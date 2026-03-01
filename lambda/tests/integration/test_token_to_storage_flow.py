"""
Integration test for Token Server -> Storage Server flow.

Tests the complete end-to-end flow:
1. Token Server receives OIDC token and generates HAWK credentials
2. HAWK credentials are stored in token cache
3. StorageHawkMiddleware validates HAWK credentials in-process
4. Storage API processes authenticated request

**Validates: Requirements 4.5, 12.1, 12.2, 12.3**
"""

import json
import time
from unittest.mock import patch

from botocore.stub import ANY

from src.entrypoint.storage_api import lambda_handler as storage_handler
from src.entrypoint.token_api import lambda_handler as token_handler
from src.services.token_generator import TokenGenerator
from tests.fixtures.integration import (
    build_hawk_auth_header,
    build_storage_event,
)


class TestTokenServerToStorageServerFlow:
    """Test end-to-end flow from Token Server to Storage Server"""

    def test_complete_token_issuance_and_validation_flow(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test complete flow: Token issuance -> HAWK middleware auth -> Storage access.

        Flow:
        1. Client sends OIDC token to Token Server
        2. Token Server validates OIDC token and issues HAWK credentials
        3. Client uses HAWK credentials to authenticate with Storage Server
        4. StorageHawkMiddleware validates credentials in-process
        5. Storage API processes request with user context

        **Validates: Requirements 4.5, 12.1, 12.2, 12.3**
        """
        # ===== Step 1-6: Token Server Issues HAWK Credentials =====

        user_id = "test-user-123"
        mock_oidc_token = "mock.oidc.token"

        token_event = {
            "httpMethod": "GET",
            "path": "/1.0/sync/1.5",
            "headers": {
                "Authorization": f"Bearer {mock_oidc_token}",
                "X-Client-State": "test-client-state-abc",
            },
            "queryStringParameters": None,
            "requestContext": {
                "requestId": "test-request-id",
                "accountId": "123456789012",
            },
        }

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
            "src.services.jwt_verifier.JWTVerifier.validate_token", return_value=mock_claims
        ):
            # UserManager.create_user() (put_item with ConditionExpression)
            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            # HawkService.store_token_in_cache()
            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Item": ANY,
                },
            )

            token_response = token_handler(
                token_event, sample_lambda_context, mock_service_provider
            )

            assert token_response["statusCode"] == 200
            token_body = json.loads(token_response["body"])

            assert "id" in token_body
            assert "key" in token_body
            assert "api_endpoint" in token_body
            assert "uid" in token_body
            assert "duration" in token_body
            assert token_body["duration"] == 300

            hawk_id = token_body["id"]
            hawk_key = token_body["key"]

            assert isinstance(hawk_id, str)
            assert len(hawk_id) > 0
            assert isinstance(hawk_key, str)
            assert len(hawk_key) == 64

        # ===== Step 7-10: Storage Server with In-Process HAWK Middleware =====

        hawk_service_instance = mock_service_provider.hawk_service
        user_id_from_hawk, generation_from_hawk, expiry_from_hawk = (
            hawk_service_instance.decode_hawk_id(hawk_id)
        )

        uid = str(TokenGenerator.generate_uid(user_id_from_hawk, generation_from_hawk))
        method = "GET"
        path = f"/1.5/{uid}/storage/bookmarks"
        host = "storage.sync.example.com"
        port = 443

        authorization_header = build_hawk_auth_header(hawk_id, hawk_key, method, path, host, port)

        storage_event = build_storage_event(
            method=method,
            path="/storage/bookmarks",
            user_id=user_id_from_hawk,
            generation=generation_from_hawk,
            headers={"Authorization": authorization_header},
            path_params={"collectionName": "bookmarks"},
        )
        storage_event["requestContext"]["domainName"] = host

        # Mock DynamoDB for hawk_service.validate (token cache lookup + nonce)
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
        )
        dynamodb_stubber.add_response(
            "put_item",
            {},
            expected_params={
                "TableName": "test-token-cache-table",
                "Item": ANY,
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        # Mock DynamoDB query for empty bookmarks collection
        dynamodb_stubber.add_response(
            "query",
            {"Items": [], "Count": 0},
            expected_params={
                "TableName": "test-storage-table",
                "KeyConditionExpression": ANY,
                "ExpressionAttributeValues": ANY,
            },
        )

        storage_response = storage_handler(
            storage_event, sample_lambda_context, mock_service_provider
        )

        assert storage_response["statusCode"] == 200
        storage_body = json.loads(storage_response["body"])
        assert storage_body == []

    def test_token_server_stores_credentials_for_middleware_validation(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that Token Server stores HAWK credentials in cache for middleware validation.

        **Validates: Requirement 4.5**
        """
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
            "src.services.jwt_verifier.JWTVerifier.validate_token", return_value=mock_claims
        ):
            # UserManager.create_user() fails - user exists
            dynamodb_stubber.add_client_error(
                "put_item",
                "ConditionalCheckFailedException",
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            # UserManager.get_user()
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
                    "Key": {"PK": f"USER#{user_id}"},
                },
            )

            # HawkService.store_token_in_cache()
            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Item": ANY,
                },
            )

            token_response = token_handler(
                token_event, sample_lambda_context, mock_service_provider
            )

            assert token_response["statusCode"] == 200
            token_body = json.loads(token_response["body"])

            hawk_id = token_body["id"]
            hawk_key = token_body["key"]

            # Verify credentials can be retrieved from cache
            hawk_service = mock_service_provider.hawk_service
            cached_user_id, cached_generation, cached_expiry = hawk_service.decode_hawk_id(hawk_id)

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
                    "Key": {"PK": f"TOKEN#{hawk_id}"},
                },
            )

            retrieved_key, retrieved_user_id, retrieved_generation = (
                hawk_service.get_hawk_key_from_cache(hawk_id)
            )

            assert retrieved_key == hawk_key
            assert retrieved_user_id == user_id
            assert retrieved_generation == 0

    def test_expired_token_rejected_by_middleware(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that expired HAWK tokens are rejected by StorageHawkMiddleware.

        **Validates: Requirement 4.5**
        """
        user_id = "test-user-789"
        generation = 0
        expiry = int(time.time()) - 100  # Expired

        hawk_service = mock_service_provider.hawk_service
        hawk_id = hawk_service.generate_hawk_id(user_id, generation, expiry)
        hawk_key = hawk_service.generate_hawk_key()

        method = "GET"
        uid = str(TokenGenerator.generate_uid(user_id, generation))
        path = f"/1.5/{uid}/storage/bookmarks"
        host = "storage.sync.example.com"

        authorization_header = build_hawk_auth_header(hawk_id, hawk_key, method, path, host, 443)

        storage_event = build_storage_event(
            method=method,
            path="/storage/bookmarks",
            user_id=user_id,
            headers={"Authorization": authorization_header},
            path_params={"collectionName": "bookmarks"},
        )
        storage_event["requestContext"]["domainName"] = host

        # Middleware should reject expired token (expiry check before DynamoDB)
        storage_response = storage_handler(
            storage_event, sample_lambda_context, mock_service_provider
        )

        assert storage_response["statusCode"] == 401

    def test_invalid_hawk_signature_rejected_by_middleware(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that invalid HAWK signatures are rejected by StorageHawkMiddleware.

        **Validates: Requirement 4.5**
        """
        user_id = "test-user-999"
        generation = 0
        expiry = int(time.time()) + 300

        hawk_service = mock_service_provider.hawk_service
        hawk_id = hawk_service.generate_hawk_id(user_id, generation, expiry)
        hawk_key = hawk_service.generate_hawk_key()

        # Build header with INVALID MAC
        authorization_header = (
            f'Hawk id="{hawk_id}", '
            f'ts="{int(time.time())}", '
            f'nonce="test-nonce-invalid", '
            f'mac="invalid-mac-signature"'
        )

        storage_event = build_storage_event(
            method="GET",
            path="/storage/bookmarks",
            user_id=user_id,
            headers={"Authorization": authorization_header},
            path_params={"collectionName": "bookmarks"},
        )
        storage_event["requestContext"]["domainName"] = "storage.sync.example.com"

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
        )

        storage_response = storage_handler(
            storage_event, sample_lambda_context, mock_service_provider
        )

        assert storage_response["statusCode"] == 401

    def test_generation_mismatch_rejected_by_middleware(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that tokens with mismatched generation numbers are rejected.

        **Validates: Requirement 4.5**
        """
        user_id = "test-user-gen"
        generation = 0
        expiry = int(time.time()) + 300

        hawk_service = mock_service_provider.hawk_service
        hawk_id = hawk_service.generate_hawk_id(user_id, generation, expiry)
        hawk_key = hawk_service.generate_hawk_key()

        uid = str(TokenGenerator.generate_uid(user_id, generation))
        method = "GET"
        path = f"/1.5/{uid}/storage/bookmarks"
        host = "storage.sync.example.com"

        authorization_header = build_hawk_auth_header(hawk_id, hawk_key, method, path, host, 443)

        storage_event = build_storage_event(
            method=method,
            path="/storage/bookmarks",
            user_id=user_id,
            headers={"Authorization": authorization_header},
            path_params={"collectionName": "bookmarks"},
        )
        storage_event["requestContext"]["domainName"] = host

        # Mock cache with DIFFERENT generation (1 instead of 0)
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"TOKEN#{hawk_id}"},
                    "hawk_key": {"S": hawk_key},
                    "user_id": {"S": user_id},
                    "generation": {"N": "1"},  # Mismatch!
                    "expiry": {"N": str(expiry)},
                    "created_at": {"N": str(int(time.time()))},
                }
            },
        )

        storage_response = storage_handler(
            storage_event, sample_lambda_context, mock_service_provider
        )

        assert storage_response["statusCode"] == 401
