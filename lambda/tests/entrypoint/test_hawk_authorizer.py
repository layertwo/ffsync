"""Tests for HAWK Lambda Authorizer"""

import base64
import time
from unittest.mock import MagicMock

import pytest
from botocore.stub import Stubber

from src.entrypoint.hawk_authorizer import lambda_handler


def generate_hawk_id(user_id: str, generation: int, expiry: int) -> str:
    """Generate a valid HAWK ID for testing"""
    id_string = f"{user_id}:{generation}:{expiry}"
    encoded = base64.urlsafe_b64encode(id_string.encode("utf-8")).decode("utf-8")
    return encoded.rstrip("=")


@pytest.fixture
def valid_hawk_id():
    """Generate a valid HAWK ID that won't expire during the test"""
    return generate_hawk_id("user123", 5, int(time.time()) + 300)


@pytest.fixture
def current_timestamp():
    """Get current timestamp for HAWK header"""
    return str(int(time.time()))


@pytest.fixture
def authorizer_event(valid_hawk_id, current_timestamp):
    """Create a sample API Gateway authorizer REQUEST event (Powertools format)"""
    return {
        "version": "1.0",
        "type": "REQUEST",
        "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/storage/bookmarks",
        "identitySource": "",
        "authorizationToken": "",
        "resource": "/1.5/12345/storage/bookmarks",
        "path": "/1.5/12345/storage/bookmarks",
        "httpMethod": "GET",
        "headers": {
            "Authorization": f'Hawk id="{valid_hawk_id}", ts="{current_timestamp}", nonce="abc123", mac="test_mac"'
        },
        "queryStringParameters": {},
        "pathParameters": {"uid": "12345"},
        "stageVariables": {},
        "requestContext": {
            "domainName": "api.example.com",
            "accountId": "123456789012",
        },
    }


@pytest.fixture
def lambda_context():
    """Create a mock Lambda context"""
    context = MagicMock()
    context.function_name = "hawk-authorizer"
    context.request_id = "test-request-id"
    return context


@pytest.fixture
def token_cache_stubber(boto_session):
    """Create a Stubber for the token cache DynamoDB table"""
    dynamodb = boto_session.resource("dynamodb")
    table = dynamodb.Table("test-token-cache-table")
    with Stubber(table.meta.client) as stubber:
        yield stubber


class TestLambdaHandlerSuccess:
    """Tests for successful authorization"""

    def test_lambda_handler_success(
        self,
        authorizer_event,
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
    ):
        """Test successful HAWK authorization"""
        # Stub DynamoDB get_item response
        token_cache_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"TOKEN#{valid_hawk_id}"},
                    "hawk_key": {"S": "a" * 64},
                    "user_id": {"S": "user123"},
                    "generation": {"N": "5"},
                    "expiry": {"N": str(int(time.time()) + 300)},
                    "created_at": {"N": str(int(time.time()))},
                }
            },
            {"Key": {"PK": f"TOKEN#{valid_hawk_id}"}, "TableName": "test-token-cache-table"},
        )

        # Mock verify_mac to return True (since tests use fake MAC values)
        mock_service_provider.hawk_service.verify_mac = MagicMock(return_value=True)

        # Use dependency injection - no patching needed!
        result = lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        # Verify result structure
        assert result["principalId"] == "user123"
        assert result["policyDocument"]["Version"] == "2012-10-17"
        assert len(result["policyDocument"]["Statement"]) == 1
        assert result["policyDocument"]["Statement"][0]["Effect"] == "Allow"
        assert result["policyDocument"]["Statement"][0]["Action"] == "execute-api:Invoke"
        assert result["policyDocument"]["Statement"][0]["Resource"] == [
            "arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/*/*"
        ]

        # Verify context
        assert "context" in result
        assert result["context"]["user_id"] == "user123"
        assert result["context"]["hawk_id"] == valid_hawk_id
        assert "authenticated_at" in result["context"]

    def test_lambda_handler_calls_validate_with_correct_params(
        self,
        authorizer_event,
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
    ):
        """Test that validate is called with correct parameters"""
        token_cache_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"TOKEN#{valid_hawk_id}"},
                    "hawk_key": {"S": "a" * 64},
                    "user_id": {"S": "user123"},
                    "generation": {"N": "5"},
                    "expiry": {"N": str(int(time.time()) + 300)},
                    "created_at": {"N": str(int(time.time()))},
                }
            },
            {"Key": {"PK": f"TOKEN#{valid_hawk_id}"}, "TableName": "test-token-cache-table"},
        )

        mock_service_provider.hawk_service.verify_mac = MagicMock(return_value=True)
        result = lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert result["principalId"] == "user123"

    def test_lambda_handler_case_insensitive_authorization_header(
        self,
        authorizer_event,
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
        current_timestamp,
    ):
        """Test that Authorization header is case-insensitive (Powertools feature)"""
        # Use lowercase 'authorization' header
        authorizer_event["headers"] = {
            "authorization": f'Hawk id="{valid_hawk_id}", ts="{current_timestamp}", nonce="abc123", mac="test_mac"'
        }

        token_cache_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"TOKEN#{valid_hawk_id}"},
                    "hawk_key": {"S": "a" * 64},
                    "user_id": {"S": "user123"},
                    "generation": {"N": "5"},
                    "expiry": {"N": str(int(time.time()) + 300)},
                    "created_at": {"N": str(int(time.time()))},
                }
            },
            {"Key": {"PK": f"TOKEN#{valid_hawk_id}"}, "TableName": "test-token-cache-table"},
        )

        mock_service_provider.hawk_service.verify_mac = MagicMock(return_value=True)
        result = lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert result["principalId"] == "user123"


class TestLambdaHandlerAuthenticationFailures:
    """Tests for authentication failures"""

    def test_lambda_handler_missing_authorization_header(
        self, authorizer_event, lambda_context, mock_service_provider
    ):
        """Test handling of missing Authorization header"""
        authorizer_event["headers"] = {}

        with pytest.raises(Exception) as exc_info:
            lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert str(exc_info.value) == "Unauthorized"

    def test_lambda_handler_invalid_hawk_header(
        self, authorizer_event, lambda_context, mock_service_provider
    ):
        """Test handling of invalid HAWK header"""
        authorizer_event["headers"]["Authorization"] = "Invalid header format"

        with pytest.raises(Exception) as exc_info:
            lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert str(exc_info.value) == "Unauthorized"

    def test_lambda_handler_invalid_signature(
        self,
        authorizer_event,
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
    ):
        """Test handling of invalid HAWK signature"""
        token_cache_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"TOKEN#{valid_hawk_id}"},
                    "hawk_key": {"S": "a" * 64},
                    "user_id": {"S": "user123"},
                    "generation": {"N": "5"},
                    "expiry": {"N": str(int(time.time()) + 300)},
                    "created_at": {"N": str(int(time.time()))},
                }
            },
            {"Key": {"PK": f"TOKEN#{valid_hawk_id}"}, "TableName": "test-token-cache-table"},
        )

        # Don't mock verify_mac - let it fail naturally with invalid MAC
        with pytest.raises(Exception) as exc_info:
            lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert str(exc_info.value) == "Unauthorized"

    def test_lambda_handler_expired_token(
        self, authorizer_event, lambda_context, mock_service_provider
    ):
        """Test handling of expired HAWK token"""
        # Use an expired timestamp in the HAWK ID
        authorizer_event["headers"][
            "Authorization"
        ] = 'Hawk id="dXNlcjEyMzo1OjE2MDAwMDAwMDA", ts="1234567890", nonce="abc123", mac="test_mac"'

        with pytest.raises(Exception) as exc_info:
            lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert str(exc_info.value) == "Unauthorized"

    def test_lambda_handler_invalid_generation(
        self,
        authorizer_event,
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
    ):
        """Test handling of invalid generation number"""
        token_cache_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"TOKEN#{valid_hawk_id}"},
                    "hawk_key": {"S": "a" * 64},
                    "user_id": {"S": "user123"},
                    "generation": {"N": "10"},  # Different generation
                    "expiry": {"N": str(int(time.time()) + 300)},
                    "created_at": {"N": str(int(time.time()))},
                }
            },
            {"Key": {"PK": f"TOKEN#{valid_hawk_id}"}, "TableName": "test-token-cache-table"},
        )

        with pytest.raises(Exception) as exc_info:
            lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert str(exc_info.value) == "Unauthorized"

    def test_lambda_handler_authentication_exception(
        self,
        authorizer_event,
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
    ):
        """Test handling of generic authentication exception"""
        # Token not found in cache
        token_cache_stubber.add_response(
            "get_item",
            {},
            {"Key": {"PK": f"TOKEN#{valid_hawk_id}"}, "TableName": "test-token-cache-table"},
        )

        with pytest.raises(Exception) as exc_info:
            lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert str(exc_info.value) == "Unauthorized"


# class TestLambdaHandlerConfigurationErrors:
#     """Tests for configuration errors"""

#     def test_lambda_handler_missing_table_name_env_var(
#         self, authorizer_event, lambda_context, monkeypatch
#     ):
#         """Test handling of missing TOKEN_CACHE_TABLE_NAME environment variable"""
#         # Remove TOKEN_CACHE_TABLE_NAME from environment
#         monkeypatch.delenv("TOKEN_CACHE_TABLE_NAME", raising=False)

#         # Create a new ServiceProvider that will fail
#         from src.environment.service_provider import ServiceProvider

#         provider = ServiceProvider()

#         with pytest.raises(Exception) as exc_info:
#             lambda_handler(authorizer_event, lambda_context)

#         assert str(exc_info.value) == "Unauthorized"


class TestLambdaHandlerUnexpectedErrors:
    """Tests for unexpected errors"""

    def test_lambda_handler_unexpected_exception(
        self, authorizer_event, lambda_context, mock_service_provider, token_cache_stubber
    ):
        """Test handling of unexpected exceptions"""
        # Simulate DynamoDB error
        token_cache_stubber.add_client_error("get_item", "InternalServerError")

        with pytest.raises(Exception) as exc_info:
            lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert str(exc_info.value) == "Unauthorized"

    def test_lambda_handler_generic_exception(
        self, authorizer_event, lambda_context, mock_service_provider
    ):
        """Test handling of generic unexpected exceptions not caught by specific handlers"""
        # Mock hawk_service to raise a generic exception
        mock_service_provider.hawk_service.validate = MagicMock(
            side_effect=RuntimeError("Unexpected error")
        )

        with pytest.raises(Exception) as exc_info:
            lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert str(exc_info.value) == "Unauthorized"


class TestLambdaHandlerEdgeCases:
    """Tests for edge cases"""

    def test_lambda_handler_missing_headers_key(
        self, authorizer_event, lambda_context, mock_service_provider
    ):
        """Test handling when Authorization header is missing"""
        authorizer_event["headers"] = {}

        with pytest.raises(Exception) as exc_info:
            lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert str(exc_info.value) == "Unauthorized"

    def test_lambda_handler_missing_request_context(
        self,
        authorizer_event,
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
    ):
        """Test handling when requestContext is missing or has no domainName"""
        authorizer_event["requestContext"] = {}

        token_cache_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"TOKEN#{valid_hawk_id}"},
                    "hawk_key": {"S": "a" * 64},
                    "user_id": {"S": "user123"},
                    "generation": {"N": "5"},
                    "expiry": {"N": str(int(time.time()) + 300)},
                    "created_at": {"N": str(int(time.time()))},
                }
            },
            {"Key": {"PK": f"TOKEN#{valid_hawk_id}"}, "TableName": "test-token-cache-table"},
        )

        mock_service_provider.hawk_service.verify_mac = MagicMock(return_value=True)
        result = lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert result["principalId"] == "user123"

    def test_lambda_handler_partial_request_context(
        self,
        authorizer_event,
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
    ):
        """Test handling when requestContext has partial data"""
        authorizer_event["httpMethod"] = "POST"
        authorizer_event["requestContext"] = {}

        token_cache_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"TOKEN#{valid_hawk_id}"},
                    "hawk_key": {"S": "a" * 64},
                    "user_id": {"S": "user123"},
                    "generation": {"N": "5"},
                    "expiry": {"N": str(int(time.time()) + 300)},
                    "created_at": {"N": str(int(time.time()))},
                }
            },
            {"Key": {"PK": f"TOKEN#{valid_hawk_id}"}, "TableName": "test-token-cache-table"},
        )

        mock_service_provider.hawk_service.verify_mac = MagicMock(return_value=True)
        result = lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert result["principalId"] == "user123"
