"""Unit tests for AccountLogin route"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.account_login import AccountLoginRoute
from src.services.fxa_crypto import derive_verify_hash


@pytest.fixture
def mock_account_manager():
    return MagicMock()


@pytest.fixture
def mock_token_manager():
    return MagicMock()


@pytest.fixture
def route(mock_account_manager, mock_token_manager):
    return AccountLoginRoute(
        account_manager=mock_account_manager,
        token_manager=mock_token_manager,
    )


def _make_account(auth_pw_hex: str) -> dict:
    """Helper to create a test account with correct verifyHash."""
    auth_pw = bytes.fromhex(auth_pw_hex)
    return {
        "uid": "uid1",
        "email": "user@example.com",
        "verifyHash": derive_verify_hash(auth_pw).hex(),
        "kA": "aa" * 32,
        "wrapKB": "bb" * 32,
        "oidcSub": "sub1",
        "verified": True,
        "createdAt": 1000,
    }


class TestAccountLogin:
    def test_success_with_keys(self, route, mock_account_manager, mock_token_manager):
        auth_pw_hex = "cc" * 32
        mock_account_manager.get_account_by_email.return_value = _make_account(auth_pw_hex)
        mock_token_manager.create_session_token.return_value = b"\xaa" * 32
        mock_token_manager.create_key_fetch_token.return_value = b"\xbb" * 32

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/login",
                "queryStringParameters": {"keys": "true"},
                "headers": {},
                "body": json.dumps({"email": "user@example.com", "authPW": auth_pw_hex}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["uid"] == "uid1"
        assert body["sessionToken"] == "aa" * 32
        assert body["keyFetchToken"] == "bb" * 32
        assert body["verified"] is True

    def test_success_without_keys(self, route, mock_account_manager, mock_token_manager):
        auth_pw_hex = "cc" * 32
        mock_account_manager.get_account_by_email.return_value = _make_account(auth_pw_hex)
        mock_token_manager.create_session_token.return_value = b"\xaa" * 32

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/login",
                "queryStringParameters": {},
                "headers": {},
                "body": json.dumps({"email": "user@example.com", "authPW": auth_pw_hex}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["uid"] == "uid1"
        assert "keyFetchToken" not in body

    def test_unknown_email_returns_400(self, route, mock_account_manager):
        mock_account_manager.get_account_by_email.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/login",
                "headers": {},
                "body": json.dumps({"email": "nobody@example.com", "authPW": "cc" * 32}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["errno"] == 102

    def test_wrong_password_returns_400(self, route, mock_account_manager):
        mock_account_manager.get_account_by_email.return_value = _make_account("cc" * 32)
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/login",
                "headers": {},
                "body": json.dumps({"email": "user@example.com", "authPW": "dd" * 32}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["errno"] == 103

    def test_invalid_json_body_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/login",
                "headers": {},
                "body": "not-json",
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_email_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/login",
                "headers": {},
                "body": json.dumps({"authPW": "cc" * 32}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_authpw_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/login",
                "headers": {},
                "body": json.dumps({"email": "user@example.com"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_body_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/login",
                "headers": {},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_invalid_authpw_format_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/login",
                "headers": {},
                "body": json.dumps({"email": "user@example.com", "authPW": "not-hex"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert "authPW" in body["message"]

    def test_invalid_email_format_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/login",
                "headers": {},
                "body": json.dumps({"email": "no-at-sign", "authPW": "cc" * 32}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert "email" in body["message"]


class TestAccountLoginBind:
    def test_bind_registers_post_route(self, route):
        mock_api = MagicMock()
        mock_api.post = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.post.assert_called_once_with("/v1/account/login")
