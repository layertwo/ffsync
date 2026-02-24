"""Unit tests for AccountCreate route"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.account_create import AccountCreateRoute
from src.shared.oidc import OIDCTokenClaims


@pytest.fixture
def mock_account_manager():
    return MagicMock()


@pytest.fixture
def mock_token_manager():
    return MagicMock()


@pytest.fixture
def mock_oidc_validator():
    return MagicMock()


@pytest.fixture
def route(mock_account_manager, mock_token_manager, mock_oidc_validator):
    return AccountCreateRoute(
        account_manager=mock_account_manager,
        token_manager=mock_token_manager,
        oidc_validator=mock_oidc_validator,
    )


@pytest.fixture
def valid_claims():
    return OIDCTokenClaims(
        sub="oidc-sub-123",
        iss="https://auth.example.com",
        aud="test-client",
        exp=9999999999,
        iat=1000000000,
        email="user@example.com",
    )


class TestAccountCreate:
    def test_success_returns_uid_and_tokens(
        self, route, mock_account_manager, mock_token_manager, mock_oidc_validator, valid_claims
    ):
        mock_oidc_validator.validate_token.return_value = valid_claims
        mock_token_manager.create_session_token.return_value = b"\xaa" * 32
        mock_token_manager.create_key_fetch_token.return_value = b"\xbb" * 32

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/create",
                "headers": {"authorization": "Bearer valid-oidc-token"},
                "body": json.dumps({"email": "user@example.com", "authPW": "cc" * 32}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert "uid" in body
        assert body["sessionToken"] == "aa" * 32
        assert body["keyFetchToken"] == "bb" * 32
        assert body["verified"] is True

    def test_missing_auth_header_returns_401(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/create",
                "headers": {},
                "body": json.dumps({"email": "user@example.com", "authPW": "cc" * 32}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_invalid_oidc_token_returns_401(self, route, mock_oidc_validator):
        mock_oidc_validator.validate_token.side_effect = Exception("Invalid token")
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/create",
                "headers": {"authorization": "Bearer bad-token"},
                "body": json.dumps({"email": "user@example.com", "authPW": "cc" * 32}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_duplicate_email_returns_409(
        self, route, mock_account_manager, mock_oidc_validator, valid_claims
    ):
        mock_oidc_validator.validate_token.return_value = valid_claims
        mock_account_manager.create_account.side_effect = ValueError("Email already exists")
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/create",
                "headers": {"authorization": "Bearer valid-token"},
                "body": json.dumps({"email": "dup@example.com", "authPW": "cc" * 32}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 409

    def test_missing_email_returns_400(self, route, mock_oidc_validator, valid_claims):
        mock_oidc_validator.validate_token.return_value = valid_claims
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/create",
                "headers": {"authorization": "Bearer valid-token"},
                "body": json.dumps({"authPW": "cc" * 32}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_authpw_returns_400(self, route, mock_oidc_validator, valid_claims):
        mock_oidc_validator.validate_token.return_value = valid_claims
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/create",
                "headers": {"authorization": "Bearer valid-token"},
                "body": json.dumps({"email": "user@example.com"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_malformed_auth_header_returns_401(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/create",
                "headers": {"authorization": "Basic dXNlcjpwYXNz"},
                "body": json.dumps({"email": "user@example.com", "authPW": "cc" * 32}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_invalid_json_body_returns_400(self, route, mock_oidc_validator, valid_claims):
        mock_oidc_validator.validate_token.return_value = valid_claims
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/create",
                "headers": {"authorization": "Bearer valid-token"},
                "body": "not json",
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_body_returns_400(self, route, mock_oidc_validator, valid_claims):
        mock_oidc_validator.validate_token.return_value = valid_claims
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/create",
                "headers": {"authorization": "Bearer valid-token"},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_creates_account_with_correct_params(
        self, route, mock_account_manager, mock_oidc_validator, mock_token_manager, valid_claims
    ):
        mock_oidc_validator.validate_token.return_value = valid_claims
        mock_token_manager.create_session_token.return_value = b"\xaa" * 32
        mock_token_manager.create_key_fetch_token.return_value = b"\xbb" * 32

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/create",
                "headers": {"authorization": "Bearer valid-token"},
                "body": json.dumps({"email": "user@example.com", "authPW": "cc" * 32}),
            }
        )
        route.handle(event)
        mock_account_manager.create_account.assert_called_once()
        call_kwargs = mock_account_manager.create_account.call_args.kwargs
        assert call_kwargs["email"] == "user@example.com"
        assert call_kwargs["oidc_sub"] == "oidc-sub-123"
        assert len(call_kwargs["verify_hash"]) == 64  # 32 bytes hex
        assert len(call_kwargs["k_a"]) == 64
        assert len(call_kwargs["wrap_kb"]) == 64
        assert len(call_kwargs["key_rotation_secret"]) == 64

    def test_invalid_authpw_format_returns_400(self, route, mock_oidc_validator, valid_claims):
        mock_oidc_validator.validate_token.return_value = valid_claims
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/create",
                "headers": {"authorization": "Bearer valid-token"},
                "body": json.dumps({"email": "user@example.com", "authPW": "not-hex"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert "authPW" in body["message"]

    def test_invalid_email_format_returns_400(self, route, mock_oidc_validator, valid_claims):
        mock_oidc_validator.validate_token.return_value = valid_claims
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/create",
                "headers": {"authorization": "Bearer valid-token"},
                "body": json.dumps({"email": "no-at-sign", "authPW": "cc" * 32}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert "email" in body["message"]


class TestAccountCreateBind:
    def test_bind_registers_post_route(self, route):
        mock_api = MagicMock()
        mock_api.post = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.post.assert_called_once_with("/v1/account/create")
