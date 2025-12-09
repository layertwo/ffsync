"""Unit tests for RequestTokenRoute"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_proxy import StatusCode

from src.routes.token.request import BEARER_TOKEN_PATTERN, RequestTokenRoute
from src.shared.exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    ServiceUnavailableError,
    ValidationException,
)
from src.shared.oidc import OIDCTokenClaims
from src.shared.token import TokenResponse
from src.shared.user import UserRecord


@pytest.fixture
def mock_oidc_validator():
    return MagicMock()


@pytest.fixture
def mock_user_manager():
    return MagicMock()


@pytest.fixture
def mock_token_generator():
    return MagicMock()


@pytest.fixture
def request_token_route(mock_oidc_validator, mock_user_manager, mock_token_generator):
    return RequestTokenRoute(
        oidc_validator=mock_oidc_validator,
        user_manager=mock_user_manager,
        token_generator=mock_token_generator,
    )


@pytest.fixture
def valid_event():
    """Valid POST request to token endpoint"""
    return {
        "httpMethod": "POST",
        "path": "/1.0/sync/1.5",
        "headers": {
            "authorization": "Bearer valid-oidc-token",
            "content-type": "application/json",
        },
        "body": None,
    }


@pytest.fixture
def mock_oidc_claims():
    return OIDCTokenClaims(
        sub="user123",
        iss="https://auth.example.com",
        aud="test-client-id",
        exp=1234567890,
        iat=1234567800,
        email="user@example.com",
    )


@pytest.fixture
def mock_user_record():
    return UserRecord(
        user_id="user123",
        generation=0,
        created_at=1234567800.0,
        updated_at=1234567800.0,
    )


@pytest.fixture
def mock_token_response():
    return TokenResponse(
        id="dXNlcjEyMzowOjEyMzQ1Njc4OTA",
        key="a" * 64,
        api_endpoint="https://sync.example.com/1.5/user123",
        uid=12345678,
        duration=300,
        hashalg="sha256",
    )


class TestRequestTokenRouteInit:
    """Test RequestTokenRoute initialization"""

    def test_init_stores_dependencies(
        self, mock_oidc_validator, mock_user_manager, mock_token_generator
    ):
        """Test that dependencies are stored correctly"""
        route = RequestTokenRoute(
            oidc_validator=mock_oidc_validator,
            user_manager=mock_user_manager,
            token_generator=mock_token_generator,
        )
        assert route.oidc_validator is mock_oidc_validator
        assert route.user_manager is mock_user_manager
        assert route.token_generator is mock_token_generator


class TestRequestTokenRouteBind:
    """Test bind method"""

    def test_bind_registers_post_route(self, request_token_route):
        """Test that bind registers POST route"""
        mock_api = MagicMock()
        mock_api.post = MagicMock(return_value=lambda f: f)
        mock_api.pass_event = MagicMock(return_value=lambda f: f)

        request_token_route.bind(mock_api)

        mock_api.post.assert_called_once_with("/1.0/sync/1.5")


class TestRequestTokenRouteHandle:
    """Test handle method"""

    def test_handle_success(
        self,
        request_token_route,
        valid_event,
        mock_oidc_claims,
        mock_user_record,
        mock_token_response,
    ):
        """Test successful token issuance"""
        request_token_route.oidc_validator.validate_token.return_value = mock_oidc_claims
        request_token_route.user_manager.get_or_create_user.return_value = mock_user_record
        request_token_route.token_generator.generate_token.return_value = mock_token_response

        response = request_token_route.handle(valid_event)

        assert response.status_code == StatusCode.OK
        assert response.content_type == "application/json"
        body = json.loads(response.body)
        assert body["id"] == mock_token_response.id
        assert body["key"] == mock_token_response.key
        assert body["api_endpoint"] == mock_token_response.api_endpoint
        assert body["uid"] == mock_token_response.uid
        assert body["duration"] == 300
        assert body["hashalg"] == "sha256"

    def test_handle_missing_auth_header(self, request_token_route):
        """Test missing Authorization header returns 401"""
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {},
        }
        response = request_token_route.handle(event)

        assert response.status_code == StatusCode.UNAUTHORIZED
        body = json.loads(response.body)
        assert body["status"] == "invalid-credentials"
        assert "Missing Authorization header" in body["errors"][0]["description"]

    def test_handle_malformed_auth_header(self, request_token_route):
        """Test malformed Authorization header returns 400"""
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {"authorization": "Basic dXNlcjpwYXNz"},
        }
        response = request_token_route.handle(event)

        assert response.status_code == StatusCode.BAD_REQUEST
        body = json.loads(response.body)
        assert body["status"] == "invalid-request"
        assert "Malformed Authorization header" in body["errors"][0]["description"]

    def test_handle_invalid_credentials_error(self, request_token_route, valid_event):
        """Test InvalidCredentialsError returns 401"""
        request_token_route.oidc_validator.validate_token.side_effect = InvalidCredentialsError(
            "Token expired"
        )

        response = request_token_route.handle(valid_event)

        assert response.status_code == StatusCode.UNAUTHORIZED
        body = json.loads(response.body)
        assert body["status"] == "invalid-credentials"

    def test_handle_invalid_token_error(self, request_token_route, valid_event):
        """Test InvalidTokenError returns 401"""
        request_token_route.oidc_validator.validate_token.side_effect = InvalidTokenError(
            "Invalid signature"
        )

        response = request_token_route.handle(valid_event)

        assert response.status_code == StatusCode.UNAUTHORIZED
        body = json.loads(response.body)
        assert body["status"] == "invalid-credentials"

    def test_handle_service_unavailable_error(self, request_token_route, valid_event):
        """Test ServiceUnavailableError returns 503"""
        request_token_route.oidc_validator.validate_token.side_effect = ServiceUnavailableError(
            "OIDC provider unreachable"
        )

        response = request_token_route.handle(valid_event)

        assert response.status_code == StatusCode.SERVICE_UNAVAILABLE
        body = json.loads(response.body)
        assert body["status"] == "service-unavailable"

    def test_handle_validation_exception(self, request_token_route, valid_event):
        """Test ValidationException returns 400"""
        request_token_route.oidc_validator.validate_token.side_effect = ValidationException(
            "Invalid request format"
        )

        response = request_token_route.handle(valid_event)

        assert response.status_code == StatusCode.BAD_REQUEST
        body = json.loads(response.body)
        assert body["status"] == "invalid-request"

    def test_handle_unexpected_error(self, request_token_route, valid_event):
        """Test unexpected error returns 500"""
        request_token_route.oidc_validator.validate_token.side_effect = RuntimeError(
            "Unexpected error"
        )

        response = request_token_route.handle(valid_event)

        assert response.status_code == StatusCode.INTERNAL_SERVER_ERROR
        body = json.loads(response.body)
        assert body["status"] == "internal-error"

    def test_handle_calls_services_in_order(
        self,
        request_token_route,
        valid_event,
        mock_oidc_claims,
        mock_user_record,
        mock_token_response,
    ):
        """Test that services are called in correct order"""
        request_token_route.oidc_validator.validate_token.return_value = mock_oidc_claims
        request_token_route.user_manager.get_or_create_user.return_value = mock_user_record
        request_token_route.token_generator.generate_token.return_value = mock_token_response

        request_token_route.handle(valid_event)

        # Verify OIDC validator was called with the token
        request_token_route.oidc_validator.validate_token.assert_called_once_with(
            "valid-oidc-token"
        )

        # Verify user manager was called with user_id from claims
        request_token_route.user_manager.get_or_create_user.assert_called_once_with("user123")

        # Verify token generator was called with user_id and generation
        request_token_route.token_generator.generate_token.assert_called_once_with(
            user_id="user123",
            generation=0,
        )

    def test_handle_null_headers(self, request_token_route):
        """Test handling of null headers"""
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": None,
        }
        response = request_token_route.handle(event)

        assert response.status_code == StatusCode.UNAUTHORIZED

    def test_handle_case_insensitive_auth_header(
        self,
        request_token_route,
        mock_oidc_claims,
        mock_user_record,
        mock_token_response,
    ):
        """Test that Authorization header lookup is case-insensitive"""
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {"Authorization": "Bearer valid-token"},
        }
        request_token_route.oidc_validator.validate_token.return_value = mock_oidc_claims
        request_token_route.user_manager.get_or_create_user.return_value = mock_user_record
        request_token_route.token_generator.generate_token.return_value = mock_token_response

        response = request_token_route.handle(event)

        assert response.status_code == StatusCode.OK


class TestExtractBearerToken:
    """Test _extract_bearer_token method"""

    def test_extract_bearer_token_valid(self, request_token_route):
        """Test extracting valid Bearer token"""
        token = request_token_route._extract_bearer_token("Bearer my-token-123")
        assert token == "my-token-123"

    def test_extract_bearer_token_case_insensitive(self, request_token_route):
        """Test Bearer keyword is case-insensitive"""
        token = request_token_route._extract_bearer_token("bearer my-token")
        assert token == "my-token"

        token = request_token_route._extract_bearer_token("BEARER my-token")
        assert token == "my-token"

    def test_extract_bearer_token_with_spaces(self, request_token_route):
        """Test token extraction with multiple spaces after Bearer"""
        # The regex \s+ consumes all whitespace between Bearer and token
        token = request_token_route._extract_bearer_token("Bearer  token-with-spaces")
        assert token == "token-with-spaces"

    def test_extract_bearer_token_invalid_format(self, request_token_route):
        """Test None returned for invalid format"""
        token = request_token_route._extract_bearer_token("Basic dXNlcjpwYXNz")
        assert token is None


class TestErrorResponse:
    """Test _error_response method"""

    def test_error_response_structure(self, request_token_route):
        """Test error response has correct structure"""
        response = request_token_route._error_response(
            status_code=StatusCode.UNAUTHORIZED,
            error_type="invalid-credentials",
            location="header",
            name="Authorization",
            description="Missing token",
        )

        assert response.status_code == StatusCode.UNAUTHORIZED
        assert response.content_type == "application/json"

        body = json.loads(response.body)
        assert body["status"] == "invalid-credentials"
        assert len(body["errors"]) == 1
        assert body["errors"][0]["location"] == "header"
        assert body["errors"][0]["name"] == "Authorization"
        assert body["errors"][0]["description"] == "Missing token"


class TestContentTypeValidation:
    """Test Content-Type validation"""

    def test_handle_invalid_content_type_returns_415(self, request_token_route):
        """Test invalid Content-Type returns 415"""
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {
                "authorization": "Bearer valid-token",
                "content-type": "application/xml",
            },
            "body": '{"some": "data"}',
        }
        response = request_token_route.handle(event)

        assert response.status_code == StatusCode.UNSUPPORTED_MEDIA_TYPE
        body = json.loads(response.body)
        assert body["status"] == "unsupported-media-type"
        assert "Content-Type" in body["errors"][0]["name"]

    def test_handle_valid_content_type_json(
        self,
        request_token_route,
        mock_oidc_claims,
        mock_user_record,
        mock_token_response,
    ):
        """Test application/json Content-Type is accepted"""
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {
                "authorization": "Bearer valid-token",
                "content-type": "application/json",
            },
            "body": '{"some": "data"}',
        }
        request_token_route.oidc_validator.validate_token.return_value = mock_oidc_claims
        request_token_route.user_manager.get_or_create_user.return_value = mock_user_record
        request_token_route.token_generator.generate_token.return_value = mock_token_response

        response = request_token_route.handle(event)

        assert response.status_code == StatusCode.OK

    def test_handle_valid_content_type_form(
        self,
        request_token_route,
        mock_oidc_claims,
        mock_user_record,
        mock_token_response,
    ):
        """Test application/x-www-form-urlencoded Content-Type is accepted"""
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {
                "authorization": "Bearer valid-token",
                "content-type": "application/x-www-form-urlencoded",
            },
            "body": "key=value",
        }
        request_token_route.oidc_validator.validate_token.return_value = mock_oidc_claims
        request_token_route.user_manager.get_or_create_user.return_value = mock_user_record
        request_token_route.token_generator.generate_token.return_value = mock_token_response

        response = request_token_route.handle(event)

        assert response.status_code == StatusCode.OK

    def test_handle_content_type_with_charset(
        self,
        request_token_route,
        mock_oidc_claims,
        mock_user_record,
        mock_token_response,
    ):
        """Test Content-Type with charset parameter is accepted"""
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {
                "authorization": "Bearer valid-token",
                "content-type": "application/json; charset=utf-8",
            },
            "body": '{"some": "data"}',
        }
        request_token_route.oidc_validator.validate_token.return_value = mock_oidc_claims
        request_token_route.user_manager.get_or_create_user.return_value = mock_user_record
        request_token_route.token_generator.generate_token.return_value = mock_token_response

        response = request_token_route.handle(event)

        assert response.status_code == StatusCode.OK

    def test_handle_no_body_skips_content_type_validation(
        self,
        request_token_route,
        mock_oidc_claims,
        mock_user_record,
        mock_token_response,
    ):
        """Test Content-Type validation is skipped when no body"""
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {
                "authorization": "Bearer valid-token",
                "content-type": "application/xml",  # Invalid but should be ignored
            },
            "body": None,
        }
        request_token_route.oidc_validator.validate_token.return_value = mock_oidc_claims
        request_token_route.user_manager.get_or_create_user.return_value = mock_user_record
        request_token_route.token_generator.generate_token.return_value = mock_token_response

        response = request_token_route.handle(event)

        assert response.status_code == StatusCode.OK

    def test_handle_empty_body_skips_content_type_validation(
        self,
        request_token_route,
        mock_oidc_claims,
        mock_user_record,
        mock_token_response,
    ):
        """Test Content-Type validation is skipped when body is empty string"""
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {
                "authorization": "Bearer valid-token",
                "content-type": "application/xml",  # Invalid but should be ignored
            },
            "body": "",
        }
        request_token_route.oidc_validator.validate_token.return_value = mock_oidc_claims
        request_token_route.user_manager.get_or_create_user.return_value = mock_user_record
        request_token_route.token_generator.generate_token.return_value = mock_token_response

        response = request_token_route.handle(event)

        assert response.status_code == StatusCode.OK


class TestBearerTokenPattern:
    """Test BEARER_TOKEN_PATTERN regex"""

    def test_pattern_matches_valid_bearer(self):
        """Test pattern matches valid Bearer tokens"""
        assert BEARER_TOKEN_PATTERN.match("Bearer token123")
        assert BEARER_TOKEN_PATTERN.match("bearer token123")
        assert BEARER_TOKEN_PATTERN.match("BEARER token123")
        assert BEARER_TOKEN_PATTERN.match("Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.xxx")

    def test_pattern_rejects_invalid_formats(self):
        """Test pattern rejects invalid formats"""
        assert not BEARER_TOKEN_PATTERN.match("Basic dXNlcjpwYXNz")
        assert not BEARER_TOKEN_PATTERN.match("token123")
        assert not BEARER_TOKEN_PATTERN.match("Bearer")  # No token
        assert not BEARER_TOKEN_PATTERN.match("")
