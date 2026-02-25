"""Unit tests for OIDC proxy routes"""

import json
from unittest.mock import MagicMock, patch

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.entrypoint import auth_api_handler
from src.routes.auth.oidc_proxy import (
    OIDCProxyConfigRoute,
    OIDCProxyTokenRoute,
    OIDCProxyUserinfoRoute,
)
from src.shared.oidc import OIDCProviderConfig


@pytest.fixture
def provider_config():
    return OIDCProviderConfig(
        issuer="https://idp.example.com",
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
        authorization_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/oauth/token",
        userinfo_endpoint="https://idp.example.com/userinfo",
    )


@pytest.fixture
def mock_oidc_validator(provider_config):
    validator = MagicMock()
    validator.discover_provider_config.return_value = provider_config
    return validator


AUTH_SERVER_BASE_URL = "https://auth.beta.ffsync.layertwo.dev"


# --- OIDCProxyConfigRoute ---


class TestOIDCProxyConfigRoute:
    @pytest.fixture
    def route(self, mock_oidc_validator):
        return OIDCProxyConfigRoute(
            oidc_validator=mock_oidc_validator,
            auth_server_base_url=AUTH_SERVER_BASE_URL,
        )

    def test_returns_config_with_proxied_endpoints(self, route):
        event = APIGatewayProxyEvent(
            {"httpMethod": "GET", "path": "/v1/oidc/config", "headers": {}}
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["issuer"] == "https://idp.example.com"
        assert body["authorization_endpoint"] == "https://idp.example.com/authorize"
        assert body["token_endpoint"] == f"{AUTH_SERVER_BASE_URL}/v1/oidc/token"
        assert body["userinfo_endpoint"] == f"{AUTH_SERVER_BASE_URL}/v1/oidc/userinfo"

    def test_returns_502_on_discovery_failure(self, mock_oidc_validator):
        mock_oidc_validator.discover_provider_config.side_effect = Exception("unreachable")
        route = OIDCProxyConfigRoute(
            oidc_validator=mock_oidc_validator,
            auth_server_base_url=AUTH_SERVER_BASE_URL,
        )
        event = APIGatewayProxyEvent(
            {"httpMethod": "GET", "path": "/v1/oidc/config", "headers": {}}
        )
        response = route.handle(event)
        assert response.status_code == 502
        body = json.loads(response.body)
        assert "error" in body

    def test_bind_registers_get_route(self, route):
        mock_api = MagicMock()
        mock_api.get = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.get.assert_called_once_with("/v1/oidc/config")


# --- OIDCProxyTokenRoute ---


class TestOIDCProxyTokenRoute:
    @pytest.fixture
    def route(self, mock_oidc_validator):
        return OIDCProxyTokenRoute(oidc_validator=mock_oidc_validator)

    @patch("src.routes.auth.oidc_proxy.http_requests")
    def test_proxies_token_exchange(self, mock_requests, route):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({"access_token": "tok123", "token_type": "Bearer"})
        mock_requests.post.return_value = mock_response

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oidc/token",
                "headers": {"Content-Type": "application/x-www-form-urlencoded"},
                "body": "grant_type=authorization_code&code=abc",
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["access_token"] == "tok123"

        mock_requests.post.assert_called_once_with(
            "https://idp.example.com/oauth/token",
            data="grant_type=authorization_code&code=abc",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )

    @patch("src.routes.auth.oidc_proxy.http_requests")
    def test_forwards_provider_error_status(self, mock_requests, route):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = json.dumps({"error": "invalid_grant"})
        mock_requests.post.return_value = mock_response

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oidc/token",
                "headers": {},
                "body": "grant_type=authorization_code&code=bad",
            }
        )
        response = route.handle(event)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["error"] == "invalid_grant"

    def test_returns_502_on_discovery_failure(self, mock_oidc_validator):
        mock_oidc_validator.discover_provider_config.side_effect = Exception("unreachable")
        route = OIDCProxyTokenRoute(oidc_validator=mock_oidc_validator)
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oidc/token",
                "headers": {},
                "body": "",
            }
        )
        response = route.handle(event)
        assert response.status_code == 502

    def test_bind_registers_post_route(self, route):
        mock_api = MagicMock()
        mock_api.post = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.post.assert_called_once_with("/v1/oidc/token")


# --- OIDCProxyUserinfoRoute ---


class TestOIDCProxyUserinfoRoute:
    @pytest.fixture
    def route(self, mock_oidc_validator):
        return OIDCProxyUserinfoRoute(oidc_validator=mock_oidc_validator)

    @patch("src.routes.auth.oidc_proxy.http_requests")
    def test_proxies_userinfo_with_auth_header(self, mock_requests, route):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({"email": "user@example.com", "sub": "abc123"})
        mock_requests.get.return_value = mock_response

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/oidc/userinfo",
                "headers": {"Authorization": "Bearer tok123"},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["email"] == "user@example.com"

        mock_requests.get.assert_called_once_with(
            "https://idp.example.com/userinfo",
            headers={"Authorization": "Bearer tok123"},
            timeout=10,
        )

    @patch("src.routes.auth.oidc_proxy.http_requests")
    def test_proxies_userinfo_without_auth_header(self, mock_requests, route):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = json.dumps({"error": "unauthorized"})
        mock_requests.get.return_value = mock_response

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/oidc/userinfo",
                "headers": {},
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

        mock_requests.get.assert_called_once_with(
            "https://idp.example.com/userinfo",
            headers={},
            timeout=10,
        )

    def test_returns_502_on_discovery_failure(self, mock_oidc_validator):
        mock_oidc_validator.discover_provider_config.side_effect = Exception("unreachable")
        route = OIDCProxyUserinfoRoute(oidc_validator=mock_oidc_validator)
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/oidc/userinfo",
                "headers": {"Authorization": "Bearer tok123"},
            }
        )
        response = route.handle(event)
        assert response.status_code == 502

    def test_bind_registers_get_route(self, route):
        mock_api = MagicMock()
        mock_api.get = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.get.assert_called_once_with("/v1/oidc/userinfo")


# --- Integration tests through the full router ---

OIDC_DISCOVERY_RESPONSE = {
    "issuer": "https://auth.example.com",
    "jwks_uri": "https://auth.example.com/jwks",
    "authorization_endpoint": "https://auth.example.com/authorize",
    "token_endpoint": "https://auth.example.com/token",
    "userinfo_endpoint": "https://auth.example.com/userinfo",
}


def _make_event(method, path, headers=None, body=None):
    return {
        "httpMethod": method,
        "path": path,
        "headers": headers or {},
        "body": body,
        "queryStringParameters": None,
        "requestContext": {"requestId": "test-request-id"},
    }


class TestOIDCProxyIntegration:
    """Integration tests that exercise proxy routes through the auth_api_handler."""

    @patch("src.routes.auth.oidc_proxy.http_requests")
    @patch("src.services.oidc_validator.requests.get")
    def test_config_route_through_router(
        self, mock_discovery_get, mock_proxy_requests, mock_service_provider, sample_lambda_context
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = OIDC_DISCOVERY_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_discovery_get.return_value = mock_resp

        result = auth_api_handler(
            _make_event("GET", "/v1/oidc/config"),
            sample_lambda_context,
            mock_service_provider,
        )
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["authorization_endpoint"] == "https://auth.example.com/authorize"
        assert "/v1/oidc/token" in body["token_endpoint"]

    @patch("src.routes.auth.oidc_proxy.http_requests")
    @patch("src.services.oidc_validator.requests.get")
    def test_token_route_through_router(
        self, mock_discovery_get, mock_proxy_requests, mock_service_provider, sample_lambda_context
    ):
        mock_disc_resp = MagicMock()
        mock_disc_resp.status_code = 200
        mock_disc_resp.json.return_value = OIDC_DISCOVERY_RESPONSE
        mock_disc_resp.raise_for_status = MagicMock()
        mock_discovery_get.return_value = mock_disc_resp

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.text = json.dumps({"access_token": "t", "token_type": "Bearer"})
        mock_proxy_requests.post.return_value = mock_token_resp

        result = auth_api_handler(
            _make_event(
                "POST",
                "/v1/oidc/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                body="grant_type=authorization_code&code=abc",
            ),
            sample_lambda_context,
            mock_service_provider,
        )
        assert result["statusCode"] == 200

    @patch("src.routes.auth.oidc_proxy.http_requests")
    @patch("src.services.oidc_validator.requests.get")
    def test_userinfo_route_through_router(
        self, mock_discovery_get, mock_proxy_requests, mock_service_provider, sample_lambda_context
    ):
        mock_disc_resp = MagicMock()
        mock_disc_resp.status_code = 200
        mock_disc_resp.json.return_value = OIDC_DISCOVERY_RESPONSE
        mock_disc_resp.raise_for_status = MagicMock()
        mock_discovery_get.return_value = mock_disc_resp

        mock_ui_resp = MagicMock()
        mock_ui_resp.status_code = 200
        mock_ui_resp.text = json.dumps({"email": "a@b.com"})
        mock_proxy_requests.get.return_value = mock_ui_resp

        result = auth_api_handler(
            _make_event("GET", "/v1/oidc/userinfo", headers={"Authorization": "Bearer tok"}),
            sample_lambda_context,
            mock_service_provider,
        )
        assert result["statusCode"] == 200
