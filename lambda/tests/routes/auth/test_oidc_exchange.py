"""Unit tests for OIDC exchange routes"""

import json
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.oidc_exchange import OIDCCodeExchangeRoute, OIDCProviderConfigRoute
from src.shared.oidc import OIDCProviderConfig
from tests.conftest import json_body

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_oidc_validator() -> MagicMock:
    validator = MagicMock()
    validator.client_id = "test-client-id"
    validator.discover_provider_config.return_value = OIDCProviderConfig(
        issuer="https://idp.example.com",
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
        authorization_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/oauth/token",
        userinfo_endpoint="https://idp.example.com/userinfo",
    )
    return validator


@pytest.fixture
def config_route(mock_oidc_validator: MagicMock) -> OIDCProviderConfigRoute:
    return OIDCProviderConfigRoute(oidc_validator=mock_oidc_validator)


@pytest.fixture
def exchange_route(
    mock_oidc_validator: MagicMock, mock_account_manager: MagicMock
) -> OIDCCodeExchangeRoute:
    return OIDCCodeExchangeRoute(
        oidc_validator=mock_oidc_validator,
        account_manager=mock_account_manager,
        user_agent="unit-test",
        metrics=MagicMock(),
    )


def _make_event(
    method: str = "GET",
    path: str = "/",
    body: Any = None,
    headers: Optional[Dict[str, str]] = None,
) -> APIGatewayProxyEvent:
    event_dict = {
        "httpMethod": method,
        "path": path,
        "headers": headers or {},
    }
    if body is not None:
        event_dict["body"] = json.dumps(body) if isinstance(body, dict) else body
    return APIGatewayProxyEvent(event_dict)


# ============================================================================
# OIDCProviderConfigRoute tests
# ============================================================================


class TestOIDCProviderConfig:
    def test_returns_authorization_endpoint(self, config_route: OIDCProviderConfigRoute) -> None:
        event = _make_event("GET", "/v1/oidc/config")
        response = config_route.handle(event)
        assert response.status_code == 200
        body = json_body(response)
        assert body["authorization_endpoint"] == "https://idp.example.com/authorize"

    def test_returns_only_authorization_endpoint(
        self, config_route: OIDCProviderConfigRoute
    ) -> None:
        event = _make_event("GET", "/v1/oidc/config")
        response = config_route.handle(event)
        body = json_body(response)
        assert list(body.keys()) == ["authorization_endpoint"]

    def test_returns_503_when_provider_unavailable(
        self, config_route: OIDCProviderConfigRoute, mock_oidc_validator: MagicMock
    ) -> None:
        mock_oidc_validator.discover_provider_config.side_effect = Exception("unreachable")
        event = _make_event("GET", "/v1/oidc/config")
        response = config_route.handle(event)
        assert response.status_code == 503
        body = json_body(response)
        assert "unavailable" in body["message"].lower()


class TestOIDCProviderConfigBind:
    def test_bind_registers_get_route(self, config_route: OIDCProviderConfigRoute) -> None:
        mock_api = MagicMock()
        mock_api.get = MagicMock(return_value=lambda f: f)
        config_route.bind(mock_api)
        mock_api.get.assert_called_once_with("/v1/oidc/config")


# ============================================================================
# OIDCCodeExchangeRoute tests
# ============================================================================


class TestOIDCCodeExchange:
    def _exchange_event(self, body: Optional[Dict[str, Any]] = None) -> APIGatewayProxyEvent:
        default_body = {
            "code": "auth-code-123",
            "code_verifier": "verifier-456",
            "redirect_uri": "https://app.example.com/callback",
        }
        return _make_event("POST", "/v1/oidc/exchange", body=body or default_body)

    @patch("src.routes.auth.oidc_exchange.requests")
    def test_success_account_exists(
        self,
        mock_requests: MagicMock,
        exchange_route: OIDCCodeExchangeRoute,
        mock_oidc_validator: MagicMock,
        mock_account_manager: MagicMock,
    ) -> None:
        # Token exchange response
        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {"access_token": "at-789"}

        # Userinfo response
        mock_userinfo_resp = MagicMock()
        mock_userinfo_resp.ok = True
        mock_userinfo_resp.json.return_value = {"email": "user@example.com"}

        mock_requests.post.return_value = mock_token_resp
        mock_requests.get.return_value = mock_userinfo_resp
        mock_requests.exceptions = __import__("requests").exceptions

        mock_oidc_validator.validate_token.return_value = MagicMock()
        mock_account_manager.get_account_by_email.return_value = {"uid": "123"}

        response = exchange_route.handle(self._exchange_event())
        assert response.status_code == 200
        body = json_body(response)
        assert body["email"] == "user@example.com"
        assert body["access_token"] == "at-789"
        assert body["account_exists"] is True

    @patch("src.routes.auth.oidc_exchange.requests")
    def test_success_account_does_not_exist(
        self,
        mock_requests: MagicMock,
        exchange_route: OIDCCodeExchangeRoute,
        mock_oidc_validator: MagicMock,
        mock_account_manager: MagicMock,
    ) -> None:
        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {"access_token": "at-789"}

        mock_userinfo_resp = MagicMock()
        mock_userinfo_resp.ok = True
        mock_userinfo_resp.json.return_value = {"email": "new@example.com"}

        mock_requests.post.return_value = mock_token_resp
        mock_requests.get.return_value = mock_userinfo_resp
        mock_requests.exceptions = __import__("requests").exceptions

        mock_oidc_validator.validate_token.return_value = MagicMock()
        mock_account_manager.get_account_by_email.return_value = None

        response = exchange_route.handle(self._exchange_event())
        assert response.status_code == 200
        body = json_body(response)
        assert body["email"] == "new@example.com"
        assert body["account_exists"] is False

    def test_invalid_json_body(self, exchange_route: OIDCCodeExchangeRoute) -> None:
        event = _make_event("POST", "/v1/oidc/exchange", body="not-json")
        response = exchange_route.handle(event)
        assert response.status_code == 400
        body = json_body(response)
        assert "Invalid JSON" in body["message"]

    def test_missing_required_fields(self, exchange_route: OIDCCodeExchangeRoute) -> None:
        event = _make_event("POST", "/v1/oidc/exchange", body={"code": "abc"})
        response = exchange_route.handle(event)
        assert response.status_code == 400
        body = json_body(response)
        assert "Missing required" in body["message"]

    def test_provider_discovery_failure(
        self, exchange_route: OIDCCodeExchangeRoute, mock_oidc_validator: MagicMock
    ) -> None:
        mock_oidc_validator.discover_provider_config.side_effect = Exception("fail")
        response = exchange_route.handle(self._exchange_event())
        assert response.status_code == 503

    @patch("src.routes.auth.oidc_exchange.requests")
    def test_token_exchange_network_error(
        self, mock_requests: MagicMock, exchange_route: OIDCCodeExchangeRoute
    ) -> None:
        import requests

        mock_requests.post.side_effect = requests.exceptions.ConnectionError("timeout")
        mock_requests.exceptions = requests.exceptions

        response = exchange_route.handle(self._exchange_event())
        assert response.status_code == 502
        body = json_body(response)
        assert "exchange" in body["message"].lower()

    @patch("src.routes.auth.oidc_exchange.requests")
    def test_token_exchange_provider_rejects(
        self, mock_requests: MagicMock, exchange_route: OIDCCodeExchangeRoute
    ) -> None:
        mock_token_resp = MagicMock()
        mock_token_resp.ok = False
        mock_token_resp.status_code = 400
        mock_token_resp.text = "invalid_grant"
        mock_requests.post.return_value = mock_token_resp
        mock_requests.exceptions = __import__("requests").exceptions

        response = exchange_route.handle(self._exchange_event())
        assert response.status_code == 401

    @patch("src.routes.auth.oidc_exchange.requests")
    def test_no_access_token_in_response(
        self, mock_requests: MagicMock, exchange_route: OIDCCodeExchangeRoute
    ) -> None:
        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {"id_token": "something"}
        mock_requests.post.return_value = mock_token_resp
        mock_requests.exceptions = __import__("requests").exceptions

        response = exchange_route.handle(self._exchange_event())
        assert response.status_code == 502
        body = json_body(response)
        assert "access token" in body["message"].lower()

    @patch("src.routes.auth.oidc_exchange.requests")
    def test_token_validation_failure(
        self,
        mock_requests: MagicMock,
        exchange_route: OIDCCodeExchangeRoute,
        mock_oidc_validator: MagicMock,
    ) -> None:
        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {"access_token": "bad-token"}
        mock_requests.post.return_value = mock_token_resp
        mock_requests.exceptions = __import__("requests").exceptions

        mock_oidc_validator.validate_token.side_effect = Exception("invalid")

        response = exchange_route.handle(self._exchange_event())
        assert response.status_code == 401

    @patch("src.routes.auth.oidc_exchange.requests")
    def test_userinfo_network_error(
        self,
        mock_requests: MagicMock,
        exchange_route: OIDCCodeExchangeRoute,
        mock_oidc_validator: MagicMock,
    ) -> None:
        import requests

        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {"access_token": "at-789"}
        mock_requests.post.return_value = mock_token_resp
        mock_requests.get.side_effect = requests.exceptions.ConnectionError("timeout")
        mock_requests.exceptions = requests.exceptions

        mock_oidc_validator.validate_token.return_value = MagicMock()

        response = exchange_route.handle(self._exchange_event())
        assert response.status_code == 502

    @patch("src.routes.auth.oidc_exchange.requests")
    def test_userinfo_provider_error(
        self,
        mock_requests: MagicMock,
        exchange_route: OIDCCodeExchangeRoute,
        mock_oidc_validator: MagicMock,
    ) -> None:
        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {"access_token": "at-789"}

        mock_userinfo_resp = MagicMock()
        mock_userinfo_resp.ok = False
        mock_userinfo_resp.status_code = 500
        mock_userinfo_resp.text = "Internal error"

        mock_requests.post.return_value = mock_token_resp
        mock_requests.get.return_value = mock_userinfo_resp
        mock_requests.exceptions = __import__("requests").exceptions

        mock_oidc_validator.validate_token.return_value = MagicMock()

        response = exchange_route.handle(self._exchange_event())
        assert response.status_code == 502

    @patch("src.routes.auth.oidc_exchange.requests")
    def test_userinfo_missing_email(
        self,
        mock_requests: MagicMock,
        exchange_route: OIDCCodeExchangeRoute,
        mock_oidc_validator: MagicMock,
    ) -> None:
        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {"access_token": "at-789"}

        mock_userinfo_resp = MagicMock()
        mock_userinfo_resp.ok = True
        mock_userinfo_resp.json.return_value = {"sub": "123"}

        mock_requests.post.return_value = mock_token_resp
        mock_requests.get.return_value = mock_userinfo_resp
        mock_requests.exceptions = __import__("requests").exceptions

        mock_oidc_validator.validate_token.return_value = MagicMock()

        response = exchange_route.handle(self._exchange_event())
        assert response.status_code == 400
        body = json_body(response)
        assert "email" in body["message"].lower()


class TestOIDCCodeExchangeBind:
    def test_bind_registers_post_route(self, exchange_route: OIDCCodeExchangeRoute) -> None:
        mock_api = MagicMock()
        mock_api.post = MagicMock(return_value=lambda f: f)
        exchange_route.bind(mock_api)
        mock_api.post.assert_called_once_with("/v1/oidc/exchange")
