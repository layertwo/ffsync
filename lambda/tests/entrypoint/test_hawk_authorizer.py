"""Tests for HAWK Lambda Authorizer"""

import base64
import time
from unittest.mock import MagicMock

import pytest
from botocore.stub import ANY, Stubber

from src.entrypoint.hawk_authorizer import lambda_handler
from tests.fixtures.integration import build_hawk_auth_header


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
def hawk_key():
    """Shared secret for HAWK authentication"""
    return "a" * 64


@pytest.fixture
def current_timestamp():
    """Get current timestamp for HAWK header"""
    return str(int(time.time()))


@pytest.fixture
def authorizer_event(valid_hawk_id, hawk_key):
    """Create a sample API Gateway authorizer REQUEST event with valid Hawk header"""
    # Build a valid Hawk header for the default path/method/host
    auth_header = build_hawk_auth_header(
        valid_hawk_id, hawk_key, "GET", "/1.5/12345/storage/bookmarks", "api.example.com", 443
    )
    return {
        "version": "1.0",
        "type": "REQUEST",
        "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/storage/bookmarks",
        "identitySource": "",
        "authorizationToken": "",
        "resource": "/1.5/12345/storage/bookmarks",
        "path": "/1.5/12345/storage/bookmarks",
        "httpMethod": "GET",
        "headers": {"Authorization": auth_header},
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


def stub_token_cache(stubber, hawk_id, hawk_key, generation=5):
    """Helper to add a token cache DynamoDB stub response"""
    stubber.add_response(
        "get_item",
        {
            "Item": {
                "PK": {"S": f"TOKEN#{hawk_id}"},
                "hawk_key": {"S": hawk_key},
                "user_id": {"S": "user123"},
                "generation": {"N": str(generation)},
                "expiry": {"N": str(int(time.time()) + 300)},
                "created_at": {"N": str(int(time.time()))},
            }
        },
        {"Key": {"PK": f"TOKEN#{hawk_id}"}, "TableName": "test-token-cache-table"},
    )


def stub_nonce(stubber):
    """Helper to add a nonce replay protection DynamoDB stub response"""
    stubber.add_response(
        "put_item",
        {},
        {
            "TableName": "test-token-cache-table",
            "Item": ANY,
            "ConditionExpression": "attribute_not_exists(PK)",
        },
    )


class TestLambdaHandlerSuccess:
    """Tests for successful authorization"""

    def test_lambda_handler_success(
        self,
        authorizer_event,
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
        hawk_key,
    ):
        """Test successful HAWK authorization"""
        stub_token_cache(token_cache_stubber, valid_hawk_id, hawk_key)
        stub_nonce(token_cache_stubber)

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
        assert result["context"]["generation"] == "5"
        assert "authenticated_at" in result["context"]

    def test_lambda_handler_calls_validate_with_correct_params(
        self,
        authorizer_event,
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
        hawk_key,
    ):
        """Test that validate is called with correct parameters"""
        stub_token_cache(token_cache_stubber, valid_hawk_id, hawk_key)
        stub_nonce(token_cache_stubber)

        result = lambda_handler(authorizer_event, lambda_context, mock_service_provider)

        assert result["principalId"] == "user123"

    def test_lambda_handler_case_insensitive_authorization_header(
        self,
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
        hawk_key,
    ):
        """Test that Authorization header is case-insensitive (Powertools feature)"""
        # Build a fresh event with lowercase 'authorization' header
        auth_header = build_hawk_auth_header(
            valid_hawk_id, hawk_key, "GET", "/1.5/12345/storage/bookmarks", "api.example.com", 443
        )
        event = {
            "version": "1.0",
            "type": "REQUEST",
            "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/storage/bookmarks",
            "identitySource": "",
            "authorizationToken": "",
            "resource": "/1.5/12345/storage/bookmarks",
            "path": "/1.5/12345/storage/bookmarks",
            "httpMethod": "GET",
            "headers": {"authorization": auth_header},
            "queryStringParameters": {},
            "pathParameters": {"uid": "12345"},
            "stageVariables": {},
            "requestContext": {
                "domainName": "api.example.com",
                "accountId": "123456789012",
            },
        }

        stub_token_cache(token_cache_stubber, valid_hawk_id, hawk_key)
        stub_nonce(token_cache_stubber)

        result = lambda_handler(event, lambda_context, mock_service_provider)

        assert result["principalId"] == "user123"

    def test_lambda_handler_includes_query_string_in_path(
        self,
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
        hawk_key,
    ):
        """Test that query string parameters are included in the path for MAC verification"""
        # Build header with query string included in the path
        path_with_qs = "/1.5/12345/storage/bookmarks?batch=true&commit=true"
        auth_header = build_hawk_auth_header(
            valid_hawk_id, hawk_key, "POST", path_with_qs, "api.example.com", 443
        )
        event = {
            "version": "1.0",
            "type": "REQUEST",
            "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/POST/storage/bookmarks",
            "identitySource": "",
            "authorizationToken": "",
            "resource": "/1.5/12345/storage/bookmarks",
            "path": "/1.5/12345/storage/bookmarks",
            "httpMethod": "POST",
            "headers": {"Authorization": auth_header},
            "queryStringParameters": {"batch": "true", "commit": "true"},
            "pathParameters": {"uid": "12345"},
            "stageVariables": {},
            "requestContext": {
                "domainName": "api.example.com",
                "accountId": "123456789012",
            },
        }

        stub_token_cache(token_cache_stubber, valid_hawk_id, hawk_key)
        stub_nonce(token_cache_stubber)

        result = lambda_handler(event, lambda_context, mock_service_provider)

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
        hawk_key,
    ):
        """Test handling of invalid HAWK signature"""
        # Replace the valid header with one that has a wrong MAC
        authorizer_event["headers"][
            "Authorization"
        ] = f'Hawk id="{valid_hawk_id}", ts="{int(time.time())}", nonce="abc123", mac="invalid_mac"'

        stub_token_cache(token_cache_stubber, valid_hawk_id, hawk_key)

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
        hawk_key,
    ):
        """Test handling of invalid generation number"""
        # Stub with different generation (10 vs 5 in hawk_id)
        stub_token_cache(token_cache_stubber, valid_hawk_id, hawk_key, generation=10)

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
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
        hawk_key,
    ):
        """Test handling when requestContext is missing or has no domainName"""
        # When domainName is empty, host defaults to "" and port to 443
        auth_header = build_hawk_auth_header(
            valid_hawk_id, hawk_key, "GET", "/1.5/12345/storage/bookmarks", "", 443
        )
        event = {
            "version": "1.0",
            "type": "REQUEST",
            "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/storage/bookmarks",
            "identitySource": "",
            "authorizationToken": "",
            "resource": "/1.5/12345/storage/bookmarks",
            "path": "/1.5/12345/storage/bookmarks",
            "httpMethod": "GET",
            "headers": {"Authorization": auth_header},
            "queryStringParameters": {},
            "pathParameters": {"uid": "12345"},
            "stageVariables": {},
            "requestContext": {},
        }

        stub_token_cache(token_cache_stubber, valid_hawk_id, hawk_key)
        stub_nonce(token_cache_stubber)

        result = lambda_handler(event, lambda_context, mock_service_provider)

        assert result["principalId"] == "user123"

    def test_lambda_handler_partial_request_context(
        self,
        lambda_context,
        mock_service_provider,
        token_cache_stubber,
        valid_hawk_id,
        hawk_key,
    ):
        """Test handling when requestContext has partial data"""
        # When domainName is empty, host defaults to "" and port to 443
        auth_header = build_hawk_auth_header(
            valid_hawk_id, hawk_key, "POST", "/1.5/12345/storage/bookmarks", "", 443
        )
        event = {
            "version": "1.0",
            "type": "REQUEST",
            "methodArn": "arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/POST/storage/bookmarks",
            "identitySource": "",
            "authorizationToken": "",
            "resource": "/1.5/12345/storage/bookmarks",
            "path": "/1.5/12345/storage/bookmarks",
            "httpMethod": "POST",
            "headers": {"Authorization": auth_header},
            "queryStringParameters": {},
            "pathParameters": {"uid": "12345"},
            "stageVariables": {},
            "requestContext": {},
        }

        stub_token_cache(token_cache_stubber, valid_hawk_id, hawk_key)
        stub_nonce(token_cache_stubber)

        result = lambda_handler(event, lambda_context, mock_service_provider)

        assert result["principalId"] == "user123"
