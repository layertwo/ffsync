"""Unit tests for OIDCDiscovery route"""

from unittest.mock import MagicMock, PropertyMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.oidc_discovery import OIDCDiscoveryRoute
from tests.conftest import json_body


@pytest.fixture
def mock_jwt_service() -> MagicMock:
    svc = MagicMock()
    type(svc).issuer = PropertyMock(return_value="https://auth.beta.ffsync.layertwo.dev")
    return svc


@pytest.fixture
def route(mock_jwt_service: MagicMock) -> OIDCDiscoveryRoute:
    return OIDCDiscoveryRoute(jwt_service=mock_jwt_service)


class TestOIDCDiscovery:
    def test_returns_discovery_document(self, route: OIDCDiscoveryRoute) -> None:
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/.well-known/openid-configuration",
                "headers": {},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json_body(response)
        assert body["issuer"] == "https://auth.beta.ffsync.layertwo.dev"
        assert body["authorization_endpoint"].endswith("/v1/oauth/authorization")
        assert body["token_endpoint"].endswith("/v1/oauth/token")
        assert body["jwks_uri"].endswith("/v1/jwks")
        assert "code" in body["response_types_supported"]
        assert "RS256" in body["id_token_signing_alg_values_supported"]


class TestOIDCDiscoveryBind:
    def test_bind_registers_get_route(self, route: OIDCDiscoveryRoute) -> None:
        mock_api = MagicMock()
        mock_api.get = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.get.assert_called_once_with("/.well-known/openid-configuration")
