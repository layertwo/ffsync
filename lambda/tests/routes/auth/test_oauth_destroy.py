"""Unit tests for OAuthDestroy route"""

import hashlib
import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.oauth_destroy import OAuthDestroyRoute


@pytest.fixture
def mock_oauth_code_manager():
    return MagicMock()


@pytest.fixture
def route(mock_oauth_code_manager):
    return OAuthDestroyRoute(oauth_code_manager=mock_oauth_code_manager)


class TestOAuthDestroy:
    def test_revokes_token_and_returns_200(self, route, mock_oauth_code_manager):
        token = "abc123"
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/destroy",
                "headers": {},
                "body": json.dumps({"token": token}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        assert json.loads(response.body) == {}
        expected_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        mock_oauth_code_manager.delete_refresh_token.assert_called_once_with(expected_hash)

    def test_returns_200_even_if_token_does_not_exist(self, route, mock_oauth_code_manager):
        """Per RFC 7009, revoking an invalid token is not an error."""
        mock_oauth_code_manager.delete_refresh_token.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/destroy",
                "headers": {},
                "body": json.dumps({"token": "nonexistent"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        assert json.loads(response.body) == {}

    def test_missing_body_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/destroy",
                "headers": {},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["errno"] == 107

    def test_invalid_json_body_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/destroy",
                "headers": {},
                "body": "not json",
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_token_field_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/destroy",
                "headers": {},
                "body": json.dumps({"client_id": "abc"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["errno"] == 107


class TestOAuthDestroyBind:
    def test_bind_registers_post_route(self, route):
        mock_api = MagicMock()
        mock_api.post = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.post.assert_called_once_with("/v1/oauth/destroy")
