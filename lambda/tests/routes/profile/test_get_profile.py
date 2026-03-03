"""Unit tests for GetProfile route"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.profile.get_profile import GetProfileRoute
from src.shared.exceptions import InvalidTokenError
from src.shared.oidc import OIDCTokenClaims


@pytest.fixture
def mock_jwt_verifier():
    return MagicMock()


@pytest.fixture
def mock_auth_account_manager():
    return MagicMock()


@pytest.fixture
def route(mock_jwt_verifier, mock_auth_account_manager):
    return GetProfileRoute(
        jwt_verifier=mock_jwt_verifier,
        auth_account_manager=mock_auth_account_manager,
    )


class TestGetProfile:
    def test_valid_bearer_token_with_fxa_uid_returns_200(
        self, route, mock_jwt_verifier, mock_auth_account_manager
    ):
        mock_jwt_verifier.validate_token.return_value = OIDCTokenClaims(
            sub="oidc-sub-123",
            iss="https://auth.example.com",
            aud="client",
            exp=9999999999,
            iat=1000000000,
            fxa_uid="uid1",
        )
        mock_auth_account_manager.get_account_by_uid.return_value = {
            "uid": "uid1",
            "email": "user@example.com",
        }
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/profile",
                "headers": {"authorization": "Bearer valid-jwt-token"},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["email"] == "user@example.com"
        assert body["uid"] == "uid1"
        assert body["locale"] == "en-US"
        assert body["avatarDefault"] is True
        assert body["sub"] == "uid1"
        mock_auth_account_manager.get_account_by_uid.assert_called_once_with("uid1")

    def test_fallback_to_oidc_sub_lookup(self, route, mock_jwt_verifier, mock_auth_account_manager):
        """When fxa_uid is absent (older token), fall back to oidcSub lookup."""
        mock_jwt_verifier.validate_token.return_value = OIDCTokenClaims(
            sub="oidc-sub-123",
            iss="https://auth.example.com",
            aud="client",
            exp=9999999999,
            iat=1000000000,
        )
        mock_auth_account_manager.get_account_by_uid.return_value = None
        mock_auth_account_manager.get_account_by_oidc_sub.return_value = {
            "uid": "uid1",
            "email": "user@example.com",
        }
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/profile",
                "headers": {"authorization": "Bearer valid-jwt-token"},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["uid"] == "uid1"
        mock_auth_account_manager.get_account_by_oidc_sub.assert_called_once_with("oidc-sub-123")

    def test_missing_auth_returns_401(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/profile",
                "headers": {},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 401
        body = json.loads(response.body)
        assert body["errno"] == 110

    def test_non_bearer_auth_returns_401(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/profile",
                "headers": {"authorization": 'Hawk id="aa"'},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 401
        body = json.loads(response.body)
        assert body["errno"] == 110

    def test_invalid_jwt_returns_401(self, route, mock_jwt_verifier):
        mock_jwt_verifier.validate_token.side_effect = InvalidTokenError("expired")
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/profile",
                "headers": {"authorization": "Bearer expired-token"},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 401
        body = json.loads(response.body)
        assert body["errno"] == 110
        assert "Invalid or expired" in body["message"]

    def test_account_not_found_returns_401(
        self, route, mock_jwt_verifier, mock_auth_account_manager
    ):
        mock_jwt_verifier.validate_token.return_value = OIDCTokenClaims(
            sub="uid-gone",
            iss="https://auth.example.com",
            aud="client",
            exp=9999999999,
            iat=1000000000,
        )
        mock_auth_account_manager.get_account_by_uid.return_value = None
        mock_auth_account_manager.get_account_by_oidc_sub.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/profile",
                "headers": {"authorization": "Bearer valid-jwt-token"},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 401
        body = json.loads(response.body)
        assert body["errno"] == 110
        assert "Account not found" in body["message"]


class TestGetProfileBind:
    def test_bind_registers_get_route(self, route):
        mock_api = MagicMock()
        mock_api.get = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.get.assert_called_once_with("/v1/profile")
