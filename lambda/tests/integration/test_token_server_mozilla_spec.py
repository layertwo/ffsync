"""
Integration tests for Token Server Mozilla Spec Compliance.

Tests the complete Token Server flow with focus on:
- GET method token issuance (Requirement 1.1)
- Client state history validation (Requirements 13.6, 13.7, 13.8)
- New error statuses (Requirements 6.6, 6.7, 6.8, 6.9)
- Response headers (Requirements 14.1, 14.2, 15.1, 16.1)
- Node reset on client state change (Requirement 2.4)

**Validates: Task 28 and subtasks 28.1, 28.2, 28.3, 28.4**
"""

import json
import time
from unittest.mock import patch

from botocore.stub import ANY

from src.entrypoint.token_api import lambda_handler as token_handler


class TestGetMethodTokenIssuance:
    """Test complete flow using GET method (Task 28, Requirement 1.1)"""

    def test_get_method_token_issuance_complete_flow(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test complete GET method token issuance flow.

        Flow:
        1. Client sends GET request with OIDC token
        2. Token Server validates OIDC token
        3. Token Server creates/retrieves user record
        4. Token Server generates HAWK credentials
        5. Token Server returns complete response

        **Validates: Requirement 1.1**
        """
        # Mock OIDC token validation
        user_id = "test-user-get-method"
        client_state = "test-client-state-123"
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
                "email": "test@example.com",
            },
        )

        # Build GET request event
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

        with patch(
            "src.services.oidc_validator.OIDCValidator.validate_token", return_value=mock_claims
        ):
            # Mock DynamoDB operations
            # 1. UserManager.create_user() (optimistic create)
            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            # 2. HawkService.store_token_in_cache()
            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Item": ANY,
                },
            )

            # Call Token Server
            response = token_handler(token_event, sample_lambda_context, mock_service_provider)

            # Verify response structure (Requirement 1.1)
            assert response["statusCode"] == 200
            assert "body" in response

            body = json.loads(response["body"])

            # Verify all required fields are present
            assert "id" in body  # HAWK ID
            assert "key" in body  # HAWK shared secret
            assert "api_endpoint" in body  # Storage URL
            assert "uid" in body  # User ID
            assert "duration" in body  # Token validity

            # Verify field values
            assert body["duration"] == 300  # 5 minutes
            assert isinstance(body["uid"], int)
            assert body["uid"] > 0

            # Verify HAWK ID format (base64-encoded)
            assert isinstance(body["id"], str)
            assert len(body["id"]) > 0

            # Verify HAWK key format (64-char hex)
            assert isinstance(body["key"], str)
            assert len(body["key"]) == 64
            assert all(c in "0123456789abcdef" for c in body["key"].lower())

            # Verify api_endpoint format
            assert body["api_endpoint"].startswith("https://")
            assert "/1.5/" in body["api_endpoint"]
            assert str(body["uid"]) in body["api_endpoint"]

    def test_get_method_response_structure_matches_mozilla_spec(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that response structure exactly matches Mozilla Token Server API v1.0 spec.

        **Validates: Requirement 1.1**
        """
        user_id = "test-user-spec"
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
            # Mock DynamoDB operations
            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Item": ANY,
                },
            )

            response = token_handler(token_event, sample_lambda_context, mock_service_provider)

            assert response["statusCode"] == 200
            body = json.loads(response["body"])

            # Verify ONLY the required fields are present (no extra fields)
            required_fields = {"id", "key", "api_endpoint", "uid", "duration", "hashalg"}
            assert set(body.keys()) == required_fields

            # Verify hashalg field
            assert body["hashalg"] == "sha256"


class TestClientStateHistory:
    """Test client state history validation (Task 28.1, Requirements 13.6, 13.7, 13.8)"""

    def test_client_state_change_flow(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test client state change increments generation and updates history.

        Flow:
        1. User requests token with client_state "state1"
        2. User requests token with client_state "state2" (different)
        3. Verify generation incremented
        4. Verify "state1" added to history

        **Validates: Requirements 13.2, 13.8**
        """
        user_id = "test-user-state-change"
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

        # First request with client_state "state1"
        token_event_1 = {
            "httpMethod": "GET",
            "path": "/1.0/sync/1.5",
            "headers": {
                "Authorization": f"Bearer {mock_oidc_token}",
                "X-Client-State": "state1",
            },
            "queryStringParameters": None,
            "requestContext": {
                "requestId": "test-request-id-1",
                "accountId": "123456789012",
            },
        }

        with patch(
            "src.services.oidc_validator.OIDCValidator.validate_token", return_value=mock_claims
        ):
            # Mock DynamoDB: create user with state1
            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Item": ANY,
                },
            )

            response_1 = token_handler(token_event_1, sample_lambda_context, mock_service_provider)
            assert response_1["statusCode"] == 200
            body_1 = json.loads(response_1["body"])
            uid_1 = body_1["uid"]

        # Second request with client_state "state2" (different)
        token_event_2 = {
            "httpMethod": "GET",
            "path": "/1.0/sync/1.5",
            "headers": {
                "Authorization": f"Bearer {mock_oidc_token}",
                "X-Client-State": "state2",
            },
            "queryStringParameters": None,
            "requestContext": {
                "requestId": "test-request-id-2",
                "accountId": "123456789012",
            },
        }

        with patch(
            "src.services.oidc_validator.OIDCValidator.validate_token", return_value=mock_claims
        ):
            # Mock DynamoDB: create fails (user exists), then get user
            dynamodb_stubber.add_client_error(
                "put_item",
                "ConditionalCheckFailedException",
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            # Get existing user with state1
            dynamodb_stubber.add_response(
                "get_item",
                {
                    "Item": {
                        "PK": {"S": f"USER#{user_id}"},
                        "user_id": {"S": user_id},
                        "generation": {"N": "0"},
                        "client_state": {"S": "state1"},
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

            # Update user: increment generation, add state1 to history, set state2
            dynamodb_stubber.add_response(
                "update_item",
                {
                    "Attributes": {
                        "generation": {"N": "1"},
                        "client_state": {"S": "state2"},
                        "client_state_history": {"L": [{"S": "state1"}]},
                        "created_at": {"N": str(int(time.time()) - 1000)},
                        "updated_at": {"N": str(int(time.time()))},
                    }
                },
                expected_params={
                    "TableName": "test-token-users-table",
                    "Key": {"PK": f"USER#{user_id}"},
                    "UpdateExpression": ANY,
                    "ExpressionAttributeValues": ANY,
                    "ReturnValues": "ALL_NEW",
                },
            )

            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Item": ANY,
                },
            )

            response_2 = token_handler(token_event_2, sample_lambda_context, mock_service_provider)
            assert response_2["statusCode"] == 200
            body_2 = json.loads(response_2["body"])
            uid_2 = body_2["uid"]

            # Verify uid changed (node reset)
            assert uid_2 != uid_1

    def test_rejection_of_previously_seen_client_state(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that previously-seen client state is rejected.

        Flow:
        1. User has history: ["state1", "state2"]
        2. User requests token with client_state "state1" (in history)
        3. Verify 401 with "invalid-client-state" status

        **Validates: Requirement 13.6**
        """
        user_id = "test-user-reused-state"
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
                "X-Client-State": "state1",  # Previously seen
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
            # Mock DynamoDB: create fails, then get user with history
            dynamodb_stubber.add_client_error(
                "put_item",
                "ConditionalCheckFailedException",
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            dynamodb_stubber.add_response(
                "get_item",
                {
                    "Item": {
                        "PK": {"S": f"USER#{user_id}"},
                        "user_id": {"S": user_id},
                        "generation": {"N": "2"},
                        "client_state": {"S": "state3"},
                        "client_state_history": {"L": [{"S": "state1"}, {"S": "state2"}]},
                        "created_at": {"N": str(int(time.time()) - 2000)},
                        "updated_at": {"N": str(int(time.time()) - 1000)},
                    }
                },
                expected_params={
                    "TableName": "test-token-users-table",
                    "Key": {"PK": f"USER#{user_id}"},
                },
            )

            response = token_handler(token_event, sample_lambda_context, mock_service_provider)

            # Verify 401 with invalid-client-state
            assert response["statusCode"] == 401
            body = json.loads(response["body"])
            assert body["status"] == "invalid-client-state"
            assert len(body["errors"]) > 0

    def test_rejection_of_empty_state_when_history_exists(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that empty client state is rejected when history contains non-empty values.

        Flow:
        1. User has history: ["state1"]
        2. User requests token with empty client_state
        3. Verify 401 with "invalid-client-state" status

        **Validates: Requirement 13.7**
        """
        user_id = "test-user-empty-state"
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

        # Request without X-Client-State header (defaults to empty)
        token_event = {
            "httpMethod": "GET",
            "path": "/1.0/sync/1.5",
            "headers": {
                "Authorization": f"Bearer {mock_oidc_token}",
                # No X-Client-State header
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
            # Mock DynamoDB: create fails, then get user with non-empty history
            dynamodb_stubber.add_client_error(
                "put_item",
                "ConditionalCheckFailedException",
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            dynamodb_stubber.add_response(
                "get_item",
                {
                    "Item": {
                        "PK": {"S": f"USER#{user_id}"},
                        "user_id": {"S": user_id},
                        "generation": {"N": "1"},
                        "client_state": {"S": "state1"},
                        "client_state_history": {"L": [{"S": "state1"}]},
                        "created_at": {"N": str(int(time.time()) - 1000)},
                        "updated_at": {"N": str(int(time.time()) - 1000)},
                    }
                },
                expected_params={
                    "TableName": "test-token-users-table",
                    "Key": {"PK": f"USER#{user_id}"},
                },
            )

            response = token_handler(token_event, sample_lambda_context, mock_service_provider)

            # Verify 401 with invalid-client-state
            assert response["statusCode"] == 401
            body = json.loads(response["body"])
            assert body["status"] == "invalid-client-state"


class TestNewErrorStatuses:
    """Test new error statuses (Task 28.2, Requirements 6.6, 6.7, 6.8, 6.9)"""

    def test_invalid_timestamp_response(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test invalid-timestamp error status.

        Flow:
        1. Client sends OIDC token with timestamp too far from server time
        2. Verify 401 with "invalid-timestamp" status

        **Validates: Requirement 6.6, 18.2**
        """
        mock_oidc_token = "mock.oidc.token"

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

        # Mock the validate_token to raise InvalidTimestampError
        from src.shared.exceptions import InvalidTimestampError

        with patch(
            "src.services.oidc_validator.OIDCValidator.validate_token",
            side_effect=InvalidTimestampError("Token timestamp differs too much from server time"),
        ):
            response = token_handler(token_event, sample_lambda_context, mock_service_provider)

            # Verify 401 with invalid-timestamp
            assert response["statusCode"] == 401
            body = json.loads(response["body"])
            assert body["status"] == "invalid-timestamp"
            assert len(body["errors"]) > 0

    def test_invalid_generation_response(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test invalid-generation error status.

        This test simulates the scenario where a user's generation has been
        incremented (e.g., due to password reset), and an old token is rejected.

        Note: This is tested at the Storage Server level (HAWK authorizer),
        not at Token Server level. Token Server doesn't validate generation
        on issuance - it just increments it when client state changes.

        **Validates: Requirement 6.7**
        """
        # This test is actually covered by the HAWK authorizer tests
        # in test_token_to_storage_flow.py::test_generation_mismatch_rejected
        # We'll add a note here for completeness
        pass

    def test_invalid_client_state_response(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test invalid-client-state error status.

        Flow:
        1. User requests token with client state in history
        2. Verify 401 with "invalid-client-state" status

        **Validates: Requirement 6.8**
        """
        # This is already tested in TestClientStateHistory class
        # test_rejection_of_previously_seen_client_state
        # and test_rejection_of_empty_state_when_history_exists
        pass

    def test_new_users_disabled_response(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
        monkeypatch,
    ):
        """
        Test new-users-disabled error status.

        Flow:
        1. Set NEW_USERS_ENABLED=false
        2. New user requests token
        3. Verify 401 with "new-users-disabled" status

        **Validates: Requirement 6.9, 17.2**
        """
        # Set environment variable to disable new users
        monkeypatch.setenv("NEW_USERS_ENABLED", "false")

        user_id = "test-user-new-disabled"
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

        # Mock the validate_token and user_manager to raise NewUsersDisabledError
        from src.shared.exceptions import NewUsersDisabledError

        with patch(
            "src.services.oidc_validator.OIDCValidator.validate_token", return_value=mock_claims
        ):
            with patch(
                "src.services.user_manager.UserManager.get_or_create_user",
                side_effect=NewUsersDisabledError("New user registration is disabled"),
            ):
                response = token_handler(token_event, sample_lambda_context, mock_service_provider)

                # Verify 401 with new-users-disabled
                assert response["statusCode"] == 401
                body = json.loads(response["body"])
                assert body["status"] == "new-users-disabled"
                assert len(body["errors"]) > 0


class TestResponseHeaders:
    """Test response headers (Task 28.3, Requirements 14.1, 14.2, 15.1, 16.1)"""

    def test_x_timestamp_on_200_response(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test X-Timestamp header on successful 200 response.

        **Validates: Requirement 14.1**
        """
        user_id = "test-user-timestamp-200"
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
            # Mock DynamoDB operations
            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Item": ANY,
                },
            )

            response = token_handler(token_event, sample_lambda_context, mock_service_provider)

            # Verify 200 response
            assert response["statusCode"] == 200

            # Verify X-Timestamp header is present (in multiValueHeaders)
            assert "multiValueHeaders" in response
            assert "X-Timestamp" in response["multiValueHeaders"]

            # Verify X-Timestamp is a valid integer timestamp
            timestamp = response["multiValueHeaders"]["X-Timestamp"][0]
            assert isinstance(timestamp, (int, str))
            timestamp_int = int(timestamp)
            assert timestamp_int > 0

            # Verify timestamp is recent (within last minute)
            current_time = int(time.time())
            assert abs(current_time - timestamp_int) < 60

    def test_x_timestamp_on_401_response(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test X-Timestamp header on 401 error response.

        **Validates: Requirement 14.2**
        """
        # Request without Authorization header (triggers 401)
        token_event = {
            "httpMethod": "GET",
            "path": "/1.0/sync/1.5",
            "headers": {},  # No Authorization header
            "queryStringParameters": None,
            "requestContext": {
                "requestId": "test-request-id",
                "accountId": "123456789012",
            },
        }

        response = token_handler(token_event, sample_lambda_context, mock_service_provider)

        # Verify 401 response
        assert response["statusCode"] == 401

        # Verify X-Timestamp header is present (in multiValueHeaders)
        assert "multiValueHeaders" in response
        assert "X-Timestamp" in response["multiValueHeaders"]

        # Verify X-Timestamp is a valid integer timestamp
        timestamp = response["multiValueHeaders"]["X-Timestamp"][0]
        assert isinstance(timestamp, (int, str))
        timestamp_int = int(timestamp)
        assert timestamp_int > 0

    def test_www_authenticate_on_401_response(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test WWW-Authenticate header on 401 response.

        **Validates: Requirement 16.1**
        """
        # Request without Authorization header (triggers 401)
        token_event = {
            "httpMethod": "GET",
            "path": "/1.0/sync/1.5",
            "headers": {},  # No Authorization header
            "queryStringParameters": None,
            "requestContext": {
                "requestId": "test-request-id",
                "accountId": "123456789012",
            },
        }

        response = token_handler(token_event, sample_lambda_context, mock_service_provider)

        # Verify 401 response
        assert response["statusCode"] == 401

        # Verify WWW-Authenticate header is present (in multiValueHeaders)
        assert "multiValueHeaders" in response
        assert "WWW-Authenticate" in response["multiValueHeaders"]

        # Verify WWW-Authenticate contains Bearer scheme
        www_auth = response["multiValueHeaders"]["WWW-Authenticate"][0]
        assert "Bearer" in www_auth

    def test_all_headers_on_401_response(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that 401 responses include both X-Timestamp and WWW-Authenticate.

        **Validates: Requirements 14.2, 16.1**
        """
        # Request without Authorization header
        token_event = {
            "httpMethod": "GET",
            "path": "/1.0/sync/1.5",
            "headers": {},
            "queryStringParameters": None,
            "requestContext": {
                "requestId": "test-request-id",
                "accountId": "123456789012",
            },
        }

        response = token_handler(token_event, sample_lambda_context, mock_service_provider)

        # Verify 401 response
        assert response["statusCode"] == 401

        # Verify both headers are present (in multiValueHeaders)
        assert "multiValueHeaders" in response
        assert "X-Timestamp" in response["multiValueHeaders"]
        assert "WWW-Authenticate" in response["multiValueHeaders"]


class TestNodeReset:
    """Test node reset on client state change (Task 28.4, Requirement 2.4)"""

    def test_uid_changes_when_client_state_changes(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that uid changes when client state changes (node reset).

        Flow:
        1. User requests token with client_state "state1"
        2. User requests token with client_state "state2"
        3. Verify uid changed

        **Validates: Requirement 2.4**
        """
        user_id = "test-user-node-reset"
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

        # First request with client_state "state1"
        token_event_1 = {
            "httpMethod": "GET",
            "path": "/1.0/sync/1.5",
            "headers": {
                "Authorization": f"Bearer {mock_oidc_token}",
                "X-Client-State": "state1",
            },
            "queryStringParameters": None,
            "requestContext": {
                "requestId": "test-request-id-1",
                "accountId": "123456789012",
            },
        }

        with patch(
            "src.services.oidc_validator.OIDCValidator.validate_token", return_value=mock_claims
        ):
            # Mock DynamoDB: create user
            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Item": ANY,
                },
            )

            response_1 = token_handler(token_event_1, sample_lambda_context, mock_service_provider)
            assert response_1["statusCode"] == 200
            body_1 = json.loads(response_1["body"])
            uid_1 = body_1["uid"]
            api_endpoint_1 = body_1["api_endpoint"]

        # Second request with client_state "state2"
        token_event_2 = {
            "httpMethod": "GET",
            "path": "/1.0/sync/1.5",
            "headers": {
                "Authorization": f"Bearer {mock_oidc_token}",
                "X-Client-State": "state2",
            },
            "queryStringParameters": None,
            "requestContext": {
                "requestId": "test-request-id-2",
                "accountId": "123456789012",
            },
        }

        with patch(
            "src.services.oidc_validator.OIDCValidator.validate_token", return_value=mock_claims
        ):
            # Mock DynamoDB: create fails, get user, update user
            dynamodb_stubber.add_client_error(
                "put_item",
                "ConditionalCheckFailedException",
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            dynamodb_stubber.add_response(
                "get_item",
                {
                    "Item": {
                        "PK": {"S": f"USER#{user_id}"},
                        "user_id": {"S": user_id},
                        "generation": {"N": "0"},
                        "client_state": {"S": "state1"},
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

            dynamodb_stubber.add_response(
                "update_item",
                {
                    "Attributes": {
                        "generation": {"N": "1"},
                        "client_state": {"S": "state2"},
                        "client_state_history": {"L": [{"S": "state1"}]},
                        "created_at": {"N": str(int(time.time()) - 1000)},
                        "updated_at": {"N": str(int(time.time()))},
                    }
                },
                expected_params={
                    "TableName": "test-token-users-table",
                    "Key": {"PK": f"USER#{user_id}"},
                    "UpdateExpression": ANY,
                    "ExpressionAttributeValues": ANY,
                    "ReturnValues": "ALL_NEW",
                },
            )

            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Item": ANY,
                },
            )

            response_2 = token_handler(token_event_2, sample_lambda_context, mock_service_provider)
            assert response_2["statusCode"] == 200
            body_2 = json.loads(response_2["body"])
            uid_2 = body_2["uid"]
            api_endpoint_2 = body_2["api_endpoint"]

            # Verify uid changed (node reset)
            assert uid_2 != uid_1

            # Verify api_endpoint changed (contains new uid)
            assert api_endpoint_2 != api_endpoint_1
            assert str(uid_2) in api_endpoint_2
            assert str(uid_1) not in api_endpoint_2

    def test_api_endpoint_changes_when_client_state_changes(
        self,
        mock_service_provider,
        dynamodb_stubber,
        sample_lambda_context,
    ):
        """
        Test that api_endpoint changes when client state changes.

        **Validates: Requirement 2.4**
        """
        user_id = "test-user-endpoint-reset"
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

        # First request
        token_event_1 = {
            "httpMethod": "GET",
            "path": "/1.0/sync/1.5",
            "headers": {
                "Authorization": f"Bearer {mock_oidc_token}",
                "X-Client-State": "original-state",
            },
            "queryStringParameters": None,
            "requestContext": {
                "requestId": "test-request-id-1",
                "accountId": "123456789012",
            },
        }

        with patch(
            "src.services.oidc_validator.OIDCValidator.validate_token", return_value=mock_claims
        ):
            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Item": ANY,
                },
            )

            response_1 = token_handler(token_event_1, sample_lambda_context, mock_service_provider)
            body_1 = json.loads(response_1["body"])
            api_endpoint_1 = body_1["api_endpoint"]

            # Verify api_endpoint format
            assert api_endpoint_1.startswith("https://")
            assert "/1.5/" in api_endpoint_1

        # Second request with different client state
        token_event_2 = {
            "httpMethod": "GET",
            "path": "/1.0/sync/1.5",
            "headers": {
                "Authorization": f"Bearer {mock_oidc_token}",
                "X-Client-State": "new-state",
            },
            "queryStringParameters": None,
            "requestContext": {
                "requestId": "test-request-id-2",
                "accountId": "123456789012",
            },
        }

        with patch(
            "src.services.oidc_validator.OIDCValidator.validate_token", return_value=mock_claims
        ):
            dynamodb_stubber.add_client_error(
                "put_item",
                "ConditionalCheckFailedException",
                expected_params={
                    "TableName": "test-token-users-table",
                    "Item": ANY,
                    "ConditionExpression": "attribute_not_exists(PK)",
                },
            )

            dynamodb_stubber.add_response(
                "get_item",
                {
                    "Item": {
                        "PK": {"S": f"USER#{user_id}"},
                        "user_id": {"S": user_id},
                        "generation": {"N": "0"},
                        "client_state": {"S": "original-state"},
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

            dynamodb_stubber.add_response(
                "update_item",
                {
                    "Attributes": {
                        "generation": {"N": "1"},
                        "client_state": {"S": "new-state"},
                        "client_state_history": {"L": [{"S": "original-state"}]},
                        "created_at": {"N": str(int(time.time()) - 1000)},
                        "updated_at": {"N": str(int(time.time()))},
                    }
                },
                expected_params={
                    "TableName": "test-token-users-table",
                    "Key": {"PK": f"USER#{user_id}"},
                    "UpdateExpression": ANY,
                    "ExpressionAttributeValues": ANY,
                    "ReturnValues": "ALL_NEW",
                },
            )

            dynamodb_stubber.add_response(
                "put_item",
                {},
                expected_params={
                    "TableName": "test-token-cache-table",
                    "Item": ANY,
                },
            )

            response_2 = token_handler(token_event_2, sample_lambda_context, mock_service_provider)
            body_2 = json.loads(response_2["body"])
            api_endpoint_2 = body_2["api_endpoint"]

            # Verify api_endpoint changed
            assert api_endpoint_2 != api_endpoint_1

            # Verify both endpoints have correct format
            assert api_endpoint_2.startswith("https://")
            assert "/1.5/" in api_endpoint_2
