"""Unit tests for JWKS route"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.jwks import JWKSRoute


@pytest.fixture
def mock_jwt_service():
    svc = MagicMock()
    svc.get_public_key_jwk.return_value = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": "abc123",
        "n": "base64url_n",
        "e": "AQAB",
    }
    return svc


@pytest.fixture
def route(mock_jwt_service):
    return JWKSRoute(jwt_service=mock_jwt_service)


class TestJWKS:
    def test_returns_jwks(self, route, mock_jwt_service):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/jwks",
                "headers": {},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert "keys" in body
        assert len(body["keys"]) == 1
        key = body["keys"][0]
        assert key["kty"] == "RSA"
        assert key["alg"] == "RS256"
        assert key["kid"] == "abc123"
        mock_jwt_service.get_public_key_jwk.assert_called_once()


class TestJWKSBind:
    def test_bind_registers_get_route(self, route):
        mock_api = MagicMock()
        mock_api.get = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.get.assert_called_once_with("/v1/jwks")
