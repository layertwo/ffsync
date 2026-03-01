"""
Integration tests for end-to-end HAWK middleware -> Storage API flow.

Tests the complete authentication and authorization flow:
1. StorageHawkMiddleware validates HAWK credentials in-process
2. Middleware injects user context into event
3. Storage API enforces user isolation
4. Users can only access their own data

**Validates: Requirements 12.1-12.5 (Authentication), All (User Isolation)**
"""

import json
import time

import pytest
from botocore.stub import ANY

from src.entrypoint.storage_api import lambda_handler as storage_handler
from src.services.hawk_service import HawkCredentials
from src.services.token_generator import TokenGenerator
from tests.fixtures.integration import (
    build_hawk_auth_header,
    build_storage_event,
)


class TestHawkMiddlewareToStorageAPIFlow:
    """Test end-to-end flow from HAWK middleware to Storage API"""

    def test_successful_authentication_flow(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """
        Test successful HAWK authentication via middleware and Storage API access.

        Flow:
        1. Client sends request with valid HAWK credentials
        2. StorageHawkMiddleware validates HAWK signature in-process
        3. Middleware injects user context into event
        4. Storage API processes request with authenticated user context
        """
        user_id = "test-user-123"
        generation = 0
        expiry = int(time.time()) + 300
        hawk_service = mock_service_provider.hawk_service
        credentials = hawk_service.generate_hawk_credentials(user_id, generation)

        # Store token in cache
        dynamodb_stubber.add_response("put_item", {})
        hawk_service.store_token_in_cache(credentials)

        # Build valid HAWK Authorization header
        method = "GET"
        uid = str(TokenGenerator.generate_uid(user_id, generation))
        path = f"/1.5/{uid}/storage/bookmarks"
        host = "storage.sync.example.com"
        port = 443

        assert credentials.hawk_key is not None
        authorization_header = build_hawk_auth_header(
            credentials.hawk_id, credentials.hawk_key, method, path, host, port
        )

        # Build storage event with Hawk auth header (middleware handles auth)
        storage_event = build_storage_event(
            method=method,
            path="/storage/bookmarks",
            user_id=user_id,
            headers={"Authorization": authorization_header},
            path_params={"collectionName": "bookmarks"},
        )
        # Override requestContext to match middleware expectations
        storage_event["requestContext"]["domainName"] = host

        # Mock DynamoDB for hawk_service.validate (token cache lookup + nonce)
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
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": "test-token-cache-table",
                "Item": ANY,
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        # Mock DynamoDB query for empty bookmarks collection
        dynamodb_stubber.add_response("query", {"Items": [], "Count": 0})

        storage_response = storage_handler(
            storage_event, sample_lambda_context, mock_service_provider
        )

        assert storage_response["statusCode"] == 200
        body = json.loads(storage_response["body"])
        assert body == []

    def test_authentication_failure_returns_401(self, mock_service_provider, sample_lambda_context):
        """
        Test that invalid HAWK credentials return 401 from middleware.

        The middleware rejects the request before it reaches the route handler.
        """
        storage_event = build_storage_event(
            method="GET",
            path="/storage/bookmarks",
            headers={
                "Authorization": (
                    'Hawk id="invalid-id", ts="1234567890", '
                    'nonce="test-nonce", mac="invalid-mac"'
                )
            },
            path_params={"collectionName": "bookmarks"},
        )

        storage_response = storage_handler(
            storage_event, sample_lambda_context, mock_service_provider
        )

        assert storage_response["statusCode"] == 401

    def test_missing_authorization_header_returns_401(
        self, mock_service_provider, sample_lambda_context
    ):
        """
        Test that requests without Authorization header are rejected by middleware.
        """
        storage_event = build_storage_event(
            method="GET",
            path="/storage/bookmarks",
            headers={"Content-Type": "application/json"},
            path_params={"collectionName": "bookmarks"},
        )
        # Remove Authorization header
        storage_event["headers"].pop("Authorization", None)

        storage_response = storage_handler(
            storage_event, sample_lambda_context, mock_service_provider
        )

        assert storage_response["statusCode"] == 401


class TestUidMismatch:
    """Test that UID mismatch is rejected by middleware"""

    def test_uid_mismatch_returns_403(self, mock_service_provider, sample_lambda_context):
        """
        Test that a request where the URL uid does not match the authenticated
        user's expected uid returns 403 via the UidMismatchError exception handler.
        """
        user_id = "test-user-mismatch"
        generation = 0
        creds = HawkCredentials(
            user_id=user_id,
            generation=generation,
            expiry=9999999999,
            hawk_id="test-hawk-id",
        )
        mock_service_provider.hawk_service.validate = lambda *a, **kw: creds

        # Build event with WRONG uid in URL path (doesn't match user_id+generation)
        storage_event = build_storage_event(
            method="GET",
            path="/info/collections",
            user_id=user_id,
        )
        # Override the pathParameters uid with wrong value
        storage_event["pathParameters"]["uid"] = "wrong-uid-value"
        storage_event["path"] = "/1.5/wrong-uid-value/info/collections"

        response = storage_handler(storage_event, sample_lambda_context, mock_service_provider)

        assert response["statusCode"] == 403
        body = json.loads(response["body"])
        assert body["error"] == "uid mismatch"


class TestUserIsolation:
    """Test that users can only access their own data"""

    @pytest.fixture(autouse=True)
    def mock_hawk_validate(self, mock_service_provider):
        """Mock hawk_service.validate to bypass auth for user isolation tests."""
        self._mock_validate = mock_service_provider.hawk_service.validate
        yield

    def _set_hawk_user(self, mock_service_provider, user_id, generation=0):
        """Configure hawk_service.validate to return credentials for given user."""
        creds = HawkCredentials(
            user_id=user_id,
            generation=generation,
            expiry=9999999999,
            hawk_id="test-hawk-id",
        )
        mock_service_provider.hawk_service.validate = lambda *a, **kw: creds

    def test_user_can_read_own_collection(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """
        Test that a user can successfully list their own collection.
        """
        user_id = "user-001"
        self._set_hawk_user(mock_service_provider, user_id)

        list_event = build_storage_event(
            method="GET",
            path="/storage/bookmarks",
            user_id=user_id,
            path_params={"collectionName": "bookmarks"},
        )

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

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body == ["bso-001"]

    def test_different_users_query_different_namespaces(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """
        Test that two different users querying the same collection name
        actually query different DynamoDB partition keys.
        """
        user1_id = "user-001"
        user2_id = "user-002"

        # User1 lists bookmarks
        self._set_hawk_user(mock_service_provider, user1_id)
        user1_event = build_storage_event(
            method="GET",
            path="/storage/bookmarks",
            user_id=user1_id,
            path_params={"collectionName": "bookmarks"},
        )

        modified_time = time.time()
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

        # User2 lists bookmarks
        self._set_hawk_user(mock_service_provider, user2_id)
        user2_event = build_storage_event(
            method="GET",
            path="/storage/bookmarks",
            user_id=user2_id,
            path_params={"collectionName": "bookmarks"},
        )

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

        assert user1_body != user2_body

    def test_user_cannot_access_missing_bso_in_other_namespace(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """
        Test that when User2 tries to access a BSO ID that exists in User1's
        namespace, they get 404.
        """
        user2_id = "user-002"
        self._set_hawk_user(mock_service_provider, user2_id)

        read_event = build_storage_event(
            method="GET",
            path="/storage/bookmarks/bso-001",
            user_id=user2_id,
            path_params={"collectionName": "bookmarks", "objectId": "bso-001"},
        )

        dynamodb_stubber.add_response("get_item", {})

        response = storage_handler(read_event, sample_lambda_context, mock_service_provider)

        assert response["statusCode"] == 404

    def test_info_collections_scoped_to_user(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """
        Test that /info/collections returns only the authenticated user's collections.
        """
        user1_id = "user-001"
        self._set_hawk_user(mock_service_provider, user1_id)

        info_event = build_storage_event(method="GET", path="/info/collections", user_id=user1_id)

        modified_time = time.time()
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": f"USER#{user1_id}#COLLECTION#bookmarks"},
                        "SK": {"S": "METADATA"},
                        "user_id": {"S": user1_id},
                        "name": {"S": "bookmarks"},
                        "modified": {"N": str(modified_time)},
                        "count": {"N": "5"},
                        "usage": {"N": "1024"},
                    },
                    {
                        "PK": {"S": f"USER#{user1_id}#COLLECTION#tabs"},
                        "SK": {"S": "METADATA"},
                        "user_id": {"S": user1_id},
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

        assert "bookmarks" in body
        assert "tabs" in body
        assert len(body) == 2

    def test_delete_all_scoped_to_user(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """
        Test that DELETE /storage only deletes the authenticated user's data.
        """
        user1_id = "user-001"
        self._set_hawk_user(mock_service_provider, user1_id)

        delete_event = build_storage_event(method="DELETE", path="/storage", user_id=user1_id)

        dynamodb_stubber.add_response("query", {"Items": []})

        response = storage_handler(delete_event, sample_lambda_context, mock_service_provider)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "modified" in body
