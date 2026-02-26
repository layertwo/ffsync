"""Unit tests for OAuthAuthorization route"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.oauth_authorization import OAuthAuthorizationRoute


@pytest.fixture
def mock_token_manager():
    return MagicMock()


@pytest.fixture
def mock_oauth_code_manager():
    return MagicMock()


@pytest.fixture
def route(mock_token_manager, mock_oauth_code_manager):
    return OAuthAuthorizationRoute(
        token_manager=mock_token_manager,
        oauth_code_manager=mock_oauth_code_manager,
    )


class TestOAuthAuthorization:
    def test_success_returns_code_and_state(
        self, route, mock_token_manager, mock_oauth_code_manager
    ):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        mock_oauth_code_manager.create_authorization_code.return_value = "auth-code-123"

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/authorization",
                "headers": {"authorization": 'Hawk id="tokenid"'},
                "body": json.dumps(
                    {
                        "client_id": "client1",
                        "scope": "https://identity.mozilla.com/apps/oldsync",
                        "state": "state123",
                        "code_challenge": "challenge",
                        "code_challenge_method": "S256",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["code"] == "auth-code-123"
        assert body["state"] == "state123"
        assert body["redirect"] == "urn:ietf:wg:oauth:2.0:oob"

    def test_missing_auth_returns_401(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/authorization",
                "headers": {},
                "body": json.dumps(
                    {
                        "client_id": "c",
                        "scope": "s",
                        "state": "st",
                        "code_challenge": "ch",
                        "code_challenge_method": "S256",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_invalid_session_token_returns_401(self, route, mock_token_manager):
        mock_token_manager.verify_session_hawk.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/authorization",
                "headers": {"authorization": 'Hawk id="bad"'},
                "body": json.dumps(
                    {
                        "client_id": "c",
                        "scope": "s",
                        "state": "st",
                        "code_challenge": "ch",
                        "code_challenge_method": "S256",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_missing_body_returns_400(self, route, mock_token_manager):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/authorization",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_client_id_returns_400(self, route, mock_token_manager):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/authorization",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": json.dumps({"scope": "s", "state": "st"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_invalid_json_body_returns_400(self, route, mock_token_manager):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/authorization",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": "not-json",
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_scope_returns_400(self, route, mock_token_manager):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/authorization",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": json.dumps({"client_id": "c", "state": "st"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_state_returns_400(self, route, mock_token_manager):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/authorization",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": json.dumps({"client_id": "c", "scope": "s"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_creates_code_with_correct_params(
        self, route, mock_token_manager, mock_oauth_code_manager
    ):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        mock_oauth_code_manager.create_authorization_code.return_value = "code"

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/authorization",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": json.dumps(
                    {
                        "client_id": "client1",
                        "scope": "openid",
                        "state": "st",
                        "code_challenge": "ch",
                        "code_challenge_method": "S256",
                    }
                ),
            }
        )
        route.handle(event)
        mock_oauth_code_manager.create_authorization_code.assert_called_once_with(
            uid="uid1",
            client_id="client1",
            scope="openid",
            code_challenge="ch",
            code_challenge_method="S256",
            keys_jwe="",
        )

    def test_passes_keys_jwe_to_code_manager(
        self, route, mock_token_manager, mock_oauth_code_manager
    ):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        mock_oauth_code_manager.create_authorization_code.return_value = "code"

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/authorization",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": json.dumps(
                    {
                        "client_id": "client1",
                        "scope": "openid",
                        "state": "st",
                        "code_challenge": "ch",
                        "code_challenge_method": "S256",
                        "keys_jwe": "encrypted-jwe-payload",
                    }
                ),
            }
        )
        route.handle(event)
        mock_oauth_code_manager.create_authorization_code.assert_called_once_with(
            uid="uid1",
            client_id="client1",
            scope="openid",
            code_challenge="ch",
            code_challenge_method="S256",
            keys_jwe="encrypted-jwe-payload",
        )


class TestOAuthAuthorizationBind:
    def test_bind_registers_post_route(self, route):
        mock_api = MagicMock()
        mock_api.post = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.post.assert_called_once_with("/v1/oauth/authorization")
