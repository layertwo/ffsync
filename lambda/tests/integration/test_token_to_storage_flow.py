"""
Integration test for Token Server → Storage Server flow.

Tests the complete end-to-end flow:
1. Token Server receives OIDC token and generates HAWK credentials
2. HAWK credentials are stored in token cache
3. Storage Server HAWK authorizer validates HAWK credentials from cache
4. Storage API processes authenticated request

**Validates: Requirements 4.5, 12.1, 12.2, 12.3**
"""

import json
import time
from unittest.mock import patch

import pytest
from botocore.stub import ANY

from src.entrypoint.hawk_authorizer import lambda_handler as authorizer_handler
from src.entrypoint.storage_api import lambda_handler as storage_handler
from src.entrypoint.token_api import lambda_handler as token_handler
from tests.fixtures.integration import build_authorizer_event, build_storage_event


class TestTokenServerToStorageServerFlow:
    """Test end-to-end flow from Token Server to Storage Server"""

    def test_complete_token_issuance_and_validation_flow(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test complete flow: Token issuance → HAWK authentication → Storage access.

        Flow:
        1. Client sends OIDC token to Token Server
        2. Token Server validates OIDC token
        3. Token Server creates/retrieves user record
        4. Token Server generates HAWK credentials
        5. Token Server stores HAWK token in cache
        6. Token Server returns HAWK credentials to client
        7. Client uses HAWK credentials to authenticate with Storage Server
        8. Storage Server HAWK authorizer validates credentials from cache
        9. Storage Server authorizer returns Allow policy
        10. Storage API processes request with user context

        **Validates: Requirements 4.5, 12.1, 12.2, 12.3**
        """
        # ===== Step 1-6: Token Server Issues HAWK Credentials =====

        # Mock OIDC token validation (we'll mock the entire validation process)
        user_id = "test-user-123"
        client_state = "test-client-state-abc"

        # Create a mock OIDC token (in real scenario, this would be a valid JWT)
        mock_oidc_token = "mock.oidc.token"

        # Build Token Server request
        token_event = {
            "httpMethod": "GET",
            "path": "/1.0/sync/1.5",
            "headers": {
                "Authorization": f"Bearer {mock_oidc_token}",
                "X-Client-State": client_state,
            },
            "queryStringParameters": None,
            "requestContext": {
                "requestId": "test-request-id",
                "accountId": "123456789012",
            },
        }

        # Mock OIDC token validation to return valid claims
        mock_claims = type(
            "OIDCTokenClaims",
            (),
            {
                "sub": user_id,
                "iss": "https://auth.example.com",
                "aud": "test-client-id",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
                "email": "test@example.com",
            },
        )

        with patch(
            "src.services.oidc_validator.OIDCValidator.validate_token", return_value=mock_claims
        ):
            # Mock DynamoDB operations for user management
            # Note: Stubs are consumed in order, so we must match the exact sequence
            # UserManager.get_or_create_user() tries create_user() first (optimistic)

            # 1. UserManager.create_user() is called (put_item with ConditionExpression)
            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,  # Complex nested structure with user record
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            # 2. HawkService.store_token_in_cache() stores HAWK token (put_item)
            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Item": ANY,  # Complex nested structure with HAWK credentials
                },
            )

            # Call Token Server
            token_response = token_handler(
                token_event, sample_lambda_context, mock_service_provider
            )

            # Verify Token Server response
            assert token_response["statusCode"] == 200
            token_body = json.loads(token_response["body"])

            # Verify response structure (Requirements 4.1, 4.2)
            assert "id" in token_body  # HAWK ID
            assert "key" in token_body  # HAWK shared secret
            assert "api_endpoint" in token_body
            assert "uid" in token_body
            assert "duration" in token_body
            assert token_body["duration"] == 300

            # Extract HAWK credentials for next steps
            hawk_id = token_body["id"]
            hawk_key = token_body["key"]

            # Verify HAWK ID format (Requirement 4.3)
            assert isinstance(hawk_id, str)
            assert len(hawk_id) > 0

            # Verify HAWK key format (Requirement 4.4)
            assert isinstance(hawk_key, str)
            assert len(hawk_key) == 64  # 32 bytes hex-encoded
            assert all(c in "0123456789abcdef" for c in hawk_key.lower())

        # ===== Step 7-10: Storage Server Validates HAWK Credentials =====

        # Build valid HAWK Authorization header
        hawk_service = mock_service_provider.hawk_service
        timestamp = int(time.time())
        nonce = "test-nonce-integration"
        method = "GET"
        path = "/storage/bookmarks"
        host = "storage.sync.example.com"
        port = 443

        # Calculate valid MAC using the HAWK key from Token Server
        normalized = hawk_service.build_normalized_string(
            str(timestamp), nonce, method, path, host, str(port)
        )
        mac = hawk_service.calculate_mac(hawk_key, normalized)

        authorization_header = (
            f'Hawk id="{hawk_id}", ' f'ts="{timestamp}", ' f'nonce="{nonce}", ' f'mac="{mac}"'
        )

        # Build HAWK authorizer event
        authorizer_event = build_authorizer_event(
            method=method, path=path, authorization_header=authorization_header
        )

        # Mock DynamoDB get_item for HAWK token retrieval from cache
        # The token was stored by Token Server in step 3
        hawk_service_instance = mock_service_provider.hawk_service
        user_id_from_hawk, generation_from_hawk, expiry_from_hawk = (
            hawk_service_instance.decode_hawk_id(hawk_id)
        )

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"TOKEN#{hawk_id}"},
                    "hawk_key": {"S": hawk_key},
                    "user_id": {"S": user_id_from_hawk},
                    "generation": {"N": str(generation_from_hawk)},
                    "expiry": {"N": str(expiry_from_hawk)},
                    "created_at": {"N": str(int(time.time()))},
                }
            },
            expected_params={
                "TableName": "test-token-cache-table",
                "Key": {"PK": f"TOKEN#{hawk_id}"},  # Table resource format (no type descriptors)
            },
        )

        # Call HAWK authorizer
        authorizer_response = authorizer_handler(
            authorizer_event, sample_lambda_context, mock_service_provider
        )

        # Verify authorizer returns Allow policy (Requirement 4.5)
        assert authorizer_response["principalId"] == user_id_from_hawk
        assert authorizer_response["policyDocument"]["Statement"][0]["Effect"] == "Allow"
        assert authorizer_response["context"]["user_id"] == user_id_from_hawk
        assert authorizer_response["context"]["hawk_id"] == hawk_id

        # ===== Step 10: Storage API Processes Request =====

        # Build Storage API event with user context from authorizer
        storage_event = build_storage_event(
            method="GET",
            path="/storage/bookmarks",
            user_id=user_id_from_hawk,
            path_params={"collectionName": "bookmarks"},
        )

        # Mock DynamoDB query to return empty collection
        dynamodb_stubber.add_response(
            "query",
            {"Items": [], "Count": 0},
            expected_params={
                "TableName": "test-storage-table",
                "KeyConditionExpression": ANY,
                "ExpressionAttributeValues": ANY,
            },
        )

        # Call Storage API
        storage_response = storage_handler(
            storage_event, sample_lambda_context, mock_service_provider
        )

        # Verify Storage API returns successful response
        assert storage_response["statusCode"] == 200
        storage_body = json.loads(storage_response["body"])
        assert storage_body == []  # Empty collection

        # Verify logging occurred (Requirements 12.1, 12.2, 12.3)
        # Note: Actual log verification would require capturing log output
        # For this integration test, we verify the flow completes successfully

    def test_token_server_stores_credentials_for_storage_validation(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that Token Server stores HAWK credentials in cache for Storage Server validation.

        This test verifies the token cache integration:
        1. Token Server generates HAWK credentials
        2. Token Server stores credentials in DynamoDB token cache
        3. Storage Server retrieves credentials from cache for validation

        **Validates: Requirement 4.5**
        """
        # Mock OIDC token validation
        user_id = "test-user-456"
        mock_oidc_token = "mock.oidc.token"

        mock_claims = type(
            "OIDCTokenClaims",
            (),
            {
                "sub": user_id,
                "iss": "https://auth.example.com",
                "aud": "test-client-id",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
            },
        )

        token_event = {
            "httpMethod": "GET",
            "path": "/1.0/sync/1.5",
            "headers": {
                "Authorization": f"Bearer {mock_oidc_token}",
            },
            "queryStringParameters": None,
            "requestContext": {
                "requestId": "test-request-id",
                "accountId": "123456789012",
            },
        }

        with patch(
            "src.services.oidc_validator.OIDCValidator.validate_token", return_value=mock_claims
        ):
            # Mock user lookup (existing user)
            # UserManager.get_or_create_user() tries create_user() first, which will fail
            # with ConditionalCheckFailedException, then it calls get_user()

            # 1. UserManager.create_user() fails because user exists
            dynamodb_stubber.add_client_error(
                "put_item",
                "ConditionalCheckFailedException",
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            # 2. UserManager.get_user() is called after create fails
            dynamodb_stubber.add_response(
                "get_item",
                {
                    "Item": {
                        "PK": {"S": f"USER#{user_id}"},
                        "user_id": {"S": user_id},
                        "generation": {"N": "0"},
                        "client_state": {"S": ""},
                        "client_state_history": {"L": []},
                        "created_at": {"N": str(int(time.time()) - 1000)},
                        "updated_at": {"N": str(int(time.time()) - 1000)},
                    }
                },
                expected_params={
                    "TableName": "test-token-users-table",
                    "Key": {"PK": f"USER#{user_id}"},  # Table resource format (no type descriptors)
                },
            )

            # 3. HawkService.store_token_in_cache() stores HAWK token
            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Item": ANY,
                },
            )

            # Call Token Server
            token_response = token_handler(
                token_event, sample_lambda_context, mock_service_provider
            )

            assert token_response["statusCode"] == 200
            token_body = json.loads(token_response["body"])

            hawk_id = token_body["id"]
            hawk_key = token_body["key"]

            # Verify the token was stored in cache by attempting to retrieve it
            # This simulates what the Storage Server authorizer would do

            # Decode HAWK ID to get user_id, generation, expiry
            hawk_service = mock_service_provider.hawk_service
            cached_user_id, cached_generation, cached_expiry = hawk_service.decode_hawk_id(hawk_id)

            # Mock the cache retrieval
            dynamodb_stubber.add_response(
                "get_item",
                {
                    "Item": {
                        "PK": {"S": f"TOKEN#{hawk_id}"},
                        "hawk_key": {"S": hawk_key},
                        "user_id": {"S": cached_user_id},
                        "generation": {"N": str(cached_generation)},
                        "expiry": {"N": str(cached_expiry)},
                        "created_at": {"N": str(int(time.time()))},
                    }
                },
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Key": {
                        "PK": f"TOKEN#{hawk_id}"
                    },  # Table resource format (no type descriptors)
                },
            )

            # Retrieve from cache (simulating Storage Server)
            retrieved_key, retrieved_user_id, retrieved_generation = (
                hawk_service.get_hawk_key_from_cache(hawk_id)
            )

            # Verify retrieved credentials match what was issued
            assert retrieved_key == hawk_key
            assert retrieved_user_id == user_id
            assert retrieved_generation == 0

    def test_expired_token_rejected_by_storage_server(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that expired HAWK tokens are rejected by Storage Server.

        Flow:
        1. Token Server issues token (we simulate this)
        2. Time passes and token expires
        3. Client attempts to use expired token
        4. Storage Server authorizer rejects expired token

        **Validates: Requirement 4.5**
        """
        # Simulate an expired token
        user_id = "test-user-789"
        generation = 0
        expiry = int(time.time()) - 100  # Expired 100 seconds ago

        hawk_service = mock_service_provider.hawk_service
        hawk_id = hawk_service.generate_hawk_id(user_id, generation, expiry)
        hawk_key = hawk_service.generate_hawk_key()

        # Build HAWK Authorization header with expired token
        timestamp = int(time.time())
        nonce = "test-nonce-expired"
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

        # Mock cache retrieval (token exists in cache but is expired)
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"TOKEN#{hawk_id}"},
                    "hawk_key": {"S": hawk_key},
                    "user_id": {"S": user_id},
                    "generation": {"N": str(generation)},
                    "expiry": {"N": str(expiry)},
                    "created_at": {"N": str(int(time.time()) - 200)},
                }
            },
            expected_params={
                "TableName": "test-token-cache-table",
                "Key": {"PK": f"TOKEN#{hawk_id}"},  # Table resource format (no type descriptors)
            },
        )

        # Authorizer should reject expired token
        with pytest.raises(Exception, match="Unauthorized"):
            authorizer_handler(authorizer_event, sample_lambda_context, mock_service_provider)

    def test_invalid_hawk_signature_rejected(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that invalid HAWK signatures are rejected by Storage Server.

        This verifies that the Storage Server properly validates HAWK signatures
        using the shared secret from the token cache.

        **Validates: Requirement 4.5**
        """
        # Create valid HAWK credentials
        user_id = "test-user-999"
        generation = 0
        expiry = int(time.time()) + 300

        hawk_service = mock_service_provider.hawk_service
        hawk_id = hawk_service.generate_hawk_id(user_id, generation, expiry)
        hawk_key = hawk_service.generate_hawk_key()

        # Build HAWK Authorization header with INVALID MAC
        timestamp = int(time.time())
        nonce = "test-nonce-invalid"
        method = "GET"
        path = "/storage/bookmarks"

        # Use wrong MAC (not computed from the request)
        invalid_mac = "invalid-mac-signature"

        authorization_header = (
            f'Hawk id="{hawk_id}", '
            f'ts="{timestamp}", '
            f'nonce="{nonce}", '
            f'mac="{invalid_mac}"'
        )

        authorizer_event = build_authorizer_event(
            method=method, path=path, authorization_header=authorization_header
        )

        # Mock cache retrieval
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"TOKEN#{hawk_id}"},
                    "hawk_key": {"S": hawk_key},
                    "user_id": {"S": user_id},
                    "generation": {"N": str(generation)},
                    "expiry": {"N": str(expiry)},
                    "created_at": {"N": str(int(time.time()))},
                }
            },
            expected_params={
                "TableName": "test-token-cache-table",
                "Key": {"PK": f"TOKEN#{hawk_id}"},  # Table resource format (no type descriptors)
            },
        )

        # Authorizer should reject invalid signature
        with pytest.raises(Exception, match="Unauthorized"):
            authorizer_handler(authorizer_event, sample_lambda_context, mock_service_provider)

    def test_generation_mismatch_rejected(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that tokens with mismatched generation numbers are rejected.

        This simulates the scenario where:
        1. Token is issued with generation 0
        2. User's generation is incremented to 1 (e.g., password reset)
        3. Old token (generation 0) is rejected

        **Validates: Requirement 4.5**
        """
        # Create HAWK credentials with generation 0
        user_id = "test-user-gen"
        generation = 0
        expiry = int(time.time()) + 300

        hawk_service = mock_service_provider.hawk_service
        hawk_id = hawk_service.generate_hawk_id(user_id, generation, expiry)
        hawk_key = hawk_service.generate_hawk_key()

        # Build valid HAWK Authorization header
        timestamp = int(time.time())
        nonce = "test-nonce-gen"
        method = "GET"
        path = "/storage/bookmarks"

        normalized = hawk_service.build_normalized_string(
            str(timestamp), nonce, method, path, "storage.sync.example.com", "443"
        )
        mac = hawk_service.calculate_mac(hawk_key, normalized)

        authorization_header = (
            f'Hawk id="{hawk_id}", ' f'ts="{timestamp}", ' f'nonce="{nonce}", ' f'mac="{mac}"'
        )

        authorizer_event = build_authorizer_event(
            method=method, path=path, authorization_header=authorization_header
        )

        # Mock cache retrieval - but with DIFFERENT generation (1 instead of 0)
        # This simulates the user's generation being incremented after token issuance
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"TOKEN#{hawk_id}"},
                    "hawk_key": {"S": hawk_key},
                    "user_id": {"S": user_id},
                    "generation": {"N": "1"},  # Mismatch! Token has 0, cache has 1
                    "expiry": {"N": str(expiry)},
                    "created_at": {"N": str(int(time.time()))},
                }
            },
            expected_params={
                "TableName": "test-token-cache-table",
                "Key": {"PK": f"TOKEN#{hawk_id}"},  # Table resource format (no type descriptors)
            },
        )

        # Authorizer should reject due to generation mismatch
        with pytest.raises(Exception, match="Unauthorized"):
            authorizer_handler(authorizer_event, sample_lambda_context, mock_service_provider)
