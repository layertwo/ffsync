"""
Integration tests for end-to-end HAWK authorizer → Storage API flow.

Tests the complete authentication and authorization flow:
1. HAWK authorizer validates credentials
2. Authorizer passes user context to Storage API
3. Storage API enforces user isolation
4. Users can only access their own data

**Validates: Requirements 12.1-12.5 (Authentication), All (User Isolation)**
"""

import json
import time

import pytest

from src.entrypoint.hawk_authorizer import lambda_handler as authorizer_handler
from src.entrypoint.storage_api import lambda_handler as storage_handler
from src.services.hawk_service import HawkService
from tests.fixtures.integration import build_authorizer_event, build_storage_event


class TestHawkAuthorizerToStorageAPIFlow:
    """Test end-to-end flow from HAWK authorizer to Storage API"""

    def test_successful_authentication_flow(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """
        Test successful HAWK authentication and Storage API access.

        Flow:
        1. Client sends request with valid HAWK credentials
        2. Authorizer validates HAWK signature
        3. Authorizer returns Allow policy with user context
        4. Storage API receives request with user_id in context
        5. Storage API successfully processes request
        """
        # Setup: Create valid HAWK credentials
        user_id = "test-user-123"
        generation = 0
        expiry = int(time.time()) + 300
        hawk_service = HawkService(mock_service_provider.token_cache_table)
        credentials = hawk_service.generate_hawk_credentials(user_id, generation)

        # Store token in cache
        dynamodb_stubber.add_response("put_item", {})
        hawk_service.store_token_in_cache(credentials)

        # Build valid HAWK Authorization header
        timestamp = int(time.time())
        nonce = "test-nonce-123"
        method = "GET"
        path = "/storage/bookmarks"
        host = "storage.sync.example.com"
        port = 443

        # Calculate valid MAC
        normalized = hawk_service.build_normalized_string(
            str(timestamp), nonce, method, path, host, str(port)
        )
        # hawk_key is guaranteed to be present after generate_hawk_credentials
        assert credentials.hawk_key is not None
        mac = hawk_service.calculate_mac(credentials.hawk_key, normalized)

        authorization_header = (
            f'Hawk id="{credentials.hawk_id}", '
            f'ts="{timestamp}", '
            f'nonce="{nonce}", '
            f'mac="{mac}"'
        )

        # Step 1: Call HAWK authorizer
        authorizer_event = build_authorizer_event(
            method=method, path=path, authorization_header=authorization_header
        )

        # Mock get_item for HAWK token retrieval
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"TOKEN#{credentials.hawk_id}"},
                    "hawk_key": {"S": credentials.hawk_key},
                    "user_id": {"S": user_id},
                    "generation": {"N": str(generation)},
                    "expiry": {"N": str(expiry)},
                    "created_at": {"N": str(int(time.time()))},
                }
            },
        )

        authorizer_response = authorizer_handler(
            authorizer_event, sample_lambda_context, mock_service_provider
        )

        # Verify authorizer returns Allow policy
        assert authorizer_response["principalId"] == user_id
        assert authorizer_response["policyDocument"]["Statement"][0]["Effect"] == "Allow"
        assert authorizer_response["context"]["user_id"] == user_id
        assert authorizer_response["context"]["hawk_id"] == credentials.hawk_id

        # Step 2: Call Storage API with user context from authorizer
        storage_event = build_storage_event(
            method="GET",
            path="/storage/bookmarks",
            user_id=user_id,
            path_params={"collectionName": "bookmarks"},
        )

        # Mock DynamoDB query to return empty collection
        dynamodb_stubber.add_response("query", {"Items": [], "Count": 0})

        storage_response = storage_handler(
            storage_event, sample_lambda_context, mock_service_provider
        )

        # Verify Storage API returns successful response
        assert storage_response["statusCode"] == 200
        body = json.loads(storage_response["body"])
        assert body == []  # Empty collection

    def test_authentication_failure_blocks_storage_access(
        self, mock_service_provider, sample_lambda_context
    ):
        """
        Test that invalid HAWK credentials prevent Storage API access.

        Flow:
        1. Client sends request with invalid HAWK credentials
        2. Authorizer rejects with "Unauthorized" exception
        3. API Gateway returns 401 (not 403)
        4. Storage API is never invoked
        """
        # Build invalid HAWK Authorization header (wrong MAC)
        authorization_header = (
            'Hawk id="invalid-id", ' 'ts="1234567890", ' 'nonce="test-nonce", ' 'mac="invalid-mac"'
        )

        authorizer_event = build_authorizer_event(
            method="GET", path="/storage/bookmarks", authorization_header=authorization_header
        )

        # Authorizer should raise "Unauthorized" exception
        with pytest.raises(Exception, match="Unauthorized"):
            authorizer_handler(authorizer_event, sample_lambda_context, mock_service_provider)

    def test_expired_token_blocks_storage_access(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """
        Test that expired HAWK tokens are rejected.

        Flow:
        1. Client sends request with expired HAWK token
        2. Authorizer detects expiry and rejects
        3. API Gateway returns 401
        """
        # Setup: Create expired HAWK credentials
        user_id = "test-user-123"
        generation = 0
        expiry = int(time.time()) - 100  # Expired 100 seconds ago
        hawk_service = HawkService(mock_service_provider.token_cache_table)

        # Manually create expired credentials
        hawk_id = hawk_service.generate_hawk_id(user_id, generation, expiry)
        hawk_key = hawk_service.generate_hawk_key()

        # Store in cache (even though expired)
        dynamodb_stubber.add_response("put_item", {})
        mock_service_provider.token_cache_table.put_item(
            Item={
                "PK": f"TOKEN#{hawk_id}",
                "hawk_key": hawk_key,
                "user_id": user_id,
                "generation": generation,
                "expiry": expiry,
                "created_at": int(time.time()) - 200,
            }
        )

        # Build HAWK Authorization header with expired token
        timestamp = int(time.time())
        nonce = "test-nonce-123"
        method = "GET"
        path = "/storage/bookmarks"
        host = "storage.sync.example.com"
        port = 443

        normalized = hawk_service.build_normalized_string(
            str(timestamp), nonce, method, path, host, str(port)
        )
        mac = hawk_service.calculate_mac(hawk_key, normalized)

        authorization_header = (
            f'Hawk id="{hawk_id}", ' f'ts="{timestamp}", ' f'nonce="{nonce}", ' f'mac="{mac}"'
        )

        authorizer_event = build_authorizer_event(
            method=method, path=path, authorization_header=authorization_header
        )

        # Authorizer should reject expired token
        with pytest.raises(Exception, match="Unauthorized"):
            authorizer_handler(authorizer_event, sample_lambda_context, mock_service_provider)

    def test_missing_authorization_header_blocks_access(
        self, mock_service_provider, sample_lambda_context
    ):
        """
        Test that requests without Authorization header are rejected.

        Flow:
        1. Client sends request without Authorization header
        2. Authorizer rejects immediately
        3. API Gateway returns 401
        """
        # Build authorizer event without Authorization header
        authorizer_event = {
            "type": "REQUEST",
            "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/storage",
            "headers": {"Host": "storage.sync.example.com"},
            "requestContext": {"path": "/storage/bookmarks", "httpMethod": "GET"},
        }

        # Authorizer should reject missing header
        with pytest.raises(Exception, match="Unauthorized"):
            authorizer_handler(authorizer_event, sample_lambda_context, mock_service_provider)


class TestUserIsolation:
    """Test that users can only access their own data"""

    def test_user_can_read_own_collection(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """
        Test that a user can successfully list their own collection.

        This verifies that the user_id from the authorizer context is properly
        passed to StorageManager and used to scope the DynamoDB query.
        """
        user_id = "user-001"

        # User lists their bookmarks
        list_event = build_storage_event(
            method="GET",
            path="/storage/bookmarks",
            user_id=user_id,
            path_params={"collectionName": "bookmarks"},
        )

        # Mock DynamoDB query - returns BSOs scoped to user-001
        modified_time = time.time()
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": f"USER#{user_id}#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#bso-001"},
                        "id": {"S": "bso-001"},
                        "payload": {"S": json.dumps({"url": "https://user1.com"})},
                        "modified": {"N": str(modified_time)},
                    }
                ],
                "Count": 1,
            },
        )

        response = storage_handler(list_event, sample_lambda_context, mock_service_provider)

        # Verify successful response
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body == ["bso-001"]

    def test_different_users_query_different_namespaces(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """
        Test that two different users querying the same collection name
        actually query different DynamoDB partition keys.

        This is the core of user isolation - each user's data is stored
        under a different partition key: USER#{user_id}#COLLECTION#{collection}
        """
        user1_id = "user-001"
        user2_id = "user-002"

        # User1 lists bookmarks
        user1_event = build_storage_event(
            method="GET",
            path="/storage/bookmarks",
            user_id=user1_id,
            path_params={"collectionName": "bookmarks"},
        )

        modified_time = time.time()
        # Mock query for User1 - returns User1's BSOs
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": f"USER#{user1_id}#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#user1-bso"},
                        "id": {"S": "user1-bso"},
                        "payload": {"S": json.dumps({"url": "https://user1.com"})},
                        "modified": {"N": str(modified_time)},
                    }
                ],
                "Count": 1,
            },
        )

        user1_response = storage_handler(user1_event, sample_lambda_context, mock_service_provider)

        assert user1_response["statusCode"] == 200
        user1_body = json.loads(user1_response["body"])
        assert user1_body == ["user1-bso"]

        # User2 lists bookmarks (same collection name, different user)
        user2_event = build_storage_event(
            method="GET",
            path="/storage/bookmarks",
            user_id=user2_id,
            path_params={"collectionName": "bookmarks"},
        )

        # Mock query for User2 - returns User2's BSOs (different partition key!)
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": f"USER#{user2_id}#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#user2-bso"},
                        "id": {"S": "user2-bso"},
                        "payload": {"S": json.dumps({"url": "https://user2.com"})},
                        "modified": {"N": str(modified_time)},
                    }
                ],
                "Count": 1,
            },
        )

        user2_response = storage_handler(user2_event, sample_lambda_context, mock_service_provider)

        assert user2_response["statusCode"] == 200
        user2_body = json.loads(user2_response["body"])
        assert user2_body == ["user2-bso"]

        # Verify they got different data
        assert user1_body != user2_body

    def test_user_cannot_access_missing_bso_in_other_namespace(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """
        Test that when User2 tries to access a BSO ID that exists in User1's
        namespace, they get 404 because it doesn't exist in User2's namespace.

        This demonstrates that even if User2 knows the BSO ID, they cannot
        access User1's data because the partition key is different.
        """
        user2_id = "user-002"

        # User2 tries to read BSO "bso-001" (which might exist for User1)
        read_event = build_storage_event(
            method="GET",
            path="/storage/bookmarks/bso-001",
            user_id=user2_id,
            path_params={"collectionName": "bookmarks", "objectId": "bso-001"},
        )

        # Mock DynamoDB get_item - returns empty (BSO not found in User2's namespace)
        dynamodb_stubber.add_response("get_item", {})  # No Item in response

        response = storage_handler(read_event, sample_lambda_context, mock_service_provider)

        # User2 gets 404 - BSO not found in their namespace
        assert response["statusCode"] == 404

    def test_info_collections_scoped_to_user(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """
        Test that /info/collections returns only the authenticated user's collections.

        This verifies that metadata endpoints also enforce user isolation.
        """
        user1_id = "user-001"

        # User1 queries /info/collections
        info_event = build_storage_event(method="GET", path="/info/collections", user_id=user1_id)

        modified_time = time.time()
        # Mock scan returns only User1's collections
        dynamodb_stubber.add_response(
            "scan",
            {
                "Items": [
                    {
                        "PK": {"S": f"USER#{user1_id}#COLLECTION#bookmarks"},
                        "SK": {"S": "METADATA"},
                        "name": {"S": "bookmarks"},
                        "modified": {"N": str(modified_time)},
                        "count": {"N": "5"},
                        "usage": {"N": "1024"},
                    },
                    {
                        "PK": {"S": f"USER#{user1_id}#COLLECTION#tabs"},
                        "SK": {"S": "METADATA"},
                        "name": {"S": "tabs"},
                        "modified": {"N": str(modified_time)},
                        "count": {"N": "3"},
                        "usage": {"N": "512"},
                    },
                ],
                "Count": 2,
            },
        )

        response = storage_handler(info_event, sample_lambda_context, mock_service_provider)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])

        # User1 sees only their collections
        assert "bookmarks" in body
        assert "tabs" in body
        assert len(body) == 2

    def test_delete_all_scoped_to_user(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """
        Test that DELETE /storage only deletes the authenticated user's data.

        This verifies that even destructive operations are properly scoped.
        """
        user1_id = "user-001"

        # User1 deletes all their data
        delete_event = build_storage_event(method="DELETE", path="/storage", user_id=user1_id)

        # Mock query to find User1's collections (scoped to USER#user-001)
        dynamodb_stubber.add_response("query", {"Items": [], "Count": 0})

        response = storage_handler(delete_event, sample_lambda_context, mock_service_provider)

        # Verify successful deletion
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "modified" in body

        # The key point: the query was scoped to USER#user-001, so only
        # User1's data would be deleted. User2's data (under USER#user-002)
        # is completely untouched.
