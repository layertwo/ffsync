"""Unit tests for OAuthAuthorization route"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.oauth_authorization import OAuthAuthorizationRoute


@pytest.fixture
def mock_oauth_code_manager():
    return MagicMock()


@pytest.fixture
def route(mock_oauth_code_manager):
    return OAuthAuthorizationRoute(
        oauth_code_manager=mock_oauth_code_manager,
        middlewares=[],
    )


def _make_event(body=None, hawk_uid="uid1"):
    """Build an event with hawk_uid pre-injected (middleware handled auth)."""
    return APIGatewayProxyEvent(
        {
            "httpMethod": "POST",
            "path": "/v1/oauth/authorization",
            "headers": {"authorization": 'Hawk id="tokenid"'},
            "body": body,
            "requestContext": {"hawk_uid": hawk_uid},
        }
    )


class TestOAuthAuthorization:
    def test_success_returns_code_and_state(self, route, mock_oauth_code_manager):
        mock_oauth_code_manager.create_authorization_code.return_value = "auth-code-123"

        event = _make_event(
            body=json.dumps(
                {
                    "client_id": "client1",
                    "scope": "https://identity.mozilla.com/apps/oldsync",
                    "state": "state123",
                    "code_challenge": "challenge",
                    "code_challenge_method": "S256",
                }
            ),
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["code"] == "auth-code-123"
        assert body["state"] == "state123"
        assert body["redirect"] == "urn:ietf:wg:oauth:2.0:oob"

    def test_missing_body_returns_400(self, route):
        event = _make_event(body=None)
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_client_id_returns_400(self, route):
        event = _make_event(
            body=json.dumps({"scope": "s", "state": "st"}),
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_invalid_json_body_returns_400(self, route):
        event = _make_event(body="not-json")
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_scope_returns_400(self, route):
        event = _make_event(
            body=json.dumps({"client_id": "c", "state": "st"}),
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_state_returns_400(self, route):
        event = _make_event(
            body=json.dumps({"client_id": "c", "scope": "s"}),
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_creates_code_with_correct_params(self, route, mock_oauth_code_manager):
        mock_oauth_code_manager.create_authorization_code.return_value = "code"

        event = _make_event(
            body=json.dumps(
                {
                    "client_id": "client1",
                    "scope": "openid",
                    "state": "st",
                    "code_challenge": "ch",
                    "code_challenge_method": "S256",
                }
            ),
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

    def test_passes_keys_jwe_to_code_manager(self, route, mock_oauth_code_manager):
        mock_oauth_code_manager.create_authorization_code.return_value = "code"

        event = _make_event(
            body=json.dumps(
                {
                    "client_id": "client1",
                    "scope": "openid",
                    "state": "st",
                    "code_challenge": "ch",
                    "code_challenge_method": "S256",
                    "keys_jwe": "encrypted-jwe-payload",
                }
            ),
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


class TestOAuthAuthorizationRedirectUri:
    def test_pairing_redirect_uri_accepted(self, route, mock_oauth_code_manager):
        """Pairing redirect_uri is accepted and returned in response."""
        mock_oauth_code_manager.create_authorization_code.return_value = "code-pair"

        event = _make_event(
            body=json.dumps(
                {
                    "client_id": "client1",
                    "scope": "openid",
                    "state": "st",
                    "redirect_uri": "urn:ietf:wg:oauth:2.0:oob:pair-auth-webchannel",
                }
            ),
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["redirect"] == "urn:ietf:wg:oauth:2.0:oob:pair-auth-webchannel"

    def test_invalid_redirect_uri_returns_400(self, route, mock_oauth_code_manager):
        """Invalid redirect_uri returns 400."""
        event = _make_event(
            body=json.dumps(
                {
                    "client_id": "client1",
                    "scope": "openid",
                    "state": "st",
                    "redirect_uri": "https://evil.example.com/callback",
                }
            ),
        )
        response = route.handle(event)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["errno"] == 107
        assert "redirect_uri" in body["message"]

    def test_default_redirect_uri_when_not_provided(self, route, mock_oauth_code_manager):
        """Default redirect_uri used when none provided."""
        mock_oauth_code_manager.create_authorization_code.return_value = "code-default"

        event = _make_event(
            body=json.dumps(
                {
                    "client_id": "client1",
                    "scope": "openid",
                    "state": "st",
                }
            ),
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["redirect"] == "urn:ietf:wg:oauth:2.0:oob"


class TestOAuthAuthorizationBind:
    def test_bind_registers_post_route(self, route):
        mock_api = MagicMock()
        mock_api.post = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.post.assert_called_once_with("/v1/oauth/authorization", middlewares=[])
