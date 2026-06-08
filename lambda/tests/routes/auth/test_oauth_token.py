"""Unit tests for OAuthToken route"""

import json
from unittest.mock import MagicMock, patch

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.oauth_token import OAuthTokenRoute


@pytest.fixture
def mock_oauth_code_manager():
    return MagicMock()


@pytest.fixture
def mock_jwt_service():
    return MagicMock()


@pytest.fixture
def mock_account_manager():
    return MagicMock()


@pytest.fixture
def mock_token_manager():
    return MagicMock()


@pytest.fixture
def route(mock_oauth_code_manager, mock_jwt_service, mock_account_manager, mock_token_manager):
    return OAuthTokenRoute(
        oauth_code_manager=mock_oauth_code_manager,
        jwt_service=mock_jwt_service,
        account_manager=mock_account_manager,
        token_manager=mock_token_manager,
        metrics=MagicMock(),
    )


class TestOAuthTokenAuthorizationCode:
    @patch(
        "src.routes.auth.oauth_token.OAuthCodeManager.verify_code_challenge",
        return_value=True,
    )
    def test_success_returns_tokens(
        self,
        mock_verify,
        route,
        mock_oauth_code_manager,
        mock_jwt_service,
        mock_account_manager,
    ):
        mock_oauth_code_manager.consume_authorization_code.return_value = {
            "uid": "uid1",
            "clientId": "client1",
            "scope": "https://identity.mozilla.com/apps/oldsync",
            "codeChallenge": "challenge",
            "codeChallengeMethod": "S256",
            "keysJwe": "some-jwe",
        }
        mock_jwt_service.sign_jwt.return_value = "jwt-access-token"
        mock_oauth_code_manager.create_refresh_token.return_value = "refresh-tok"
        mock_account_manager.get_account_by_uid.return_value = {
            "uid": "uid1",
            "oidcSub": "oidc-sub-123",
        }

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps(
                    {
                        "grant_type": "authorization_code",
                        "code": "auth-code-123",
                        "code_verifier": "verifier",
                        "client_id": "client1",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["access_token"] == "jwt-access-token"
        assert body["refresh_token"] == "refresh-tok"
        assert body["token_type"] == "bearer"
        assert "expires_in" in body
        assert body["scope"] == "https://identity.mozilla.com/apps/oldsync"
        assert body["keys_jwe"] == "some-jwe"

    @patch(
        "src.routes.auth.oauth_token.OAuthCodeManager.verify_code_challenge",
        return_value=True,
    )
    def test_omits_keys_jwe_when_empty(
        self,
        mock_verify,
        route,
        mock_oauth_code_manager,
        mock_jwt_service,
        mock_account_manager,
    ):
        mock_oauth_code_manager.consume_authorization_code.return_value = {
            "uid": "uid1",
            "clientId": "client1",
            "scope": "openid",
            "codeChallenge": "challenge",
            "codeChallengeMethod": "S256",
            "keysJwe": "",
        }
        mock_jwt_service.sign_jwt.return_value = "jwt"
        mock_oauth_code_manager.create_refresh_token.return_value = "refresh"
        mock_account_manager.get_account_by_uid.return_value = {
            "uid": "uid1",
            "oidcSub": "sub1",
        }

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps(
                    {
                        "grant_type": "authorization_code",
                        "code": "code",
                        "code_verifier": "verifier",
                        "client_id": "client1",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert "keys_jwe" not in body

    def test_invalid_code_returns_400(self, route, mock_oauth_code_manager):
        mock_oauth_code_manager.consume_authorization_code.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps(
                    {
                        "grant_type": "authorization_code",
                        "code": "bad-code",
                        "code_verifier": "v",
                        "client_id": "c",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    @patch(
        "src.routes.auth.oauth_token.OAuthCodeManager.verify_code_challenge",
        return_value=False,
    )
    def test_invalid_pkce_returns_400(
        self, mock_verify, route, mock_oauth_code_manager, mock_account_manager
    ):
        mock_oauth_code_manager.consume_authorization_code.return_value = {
            "uid": "uid1",
            "clientId": "client1",
            "scope": "openid",
            "codeChallenge": "challenge",
            "codeChallengeMethod": "S256",
        }
        mock_account_manager.get_account_by_uid.return_value = {
            "uid": "uid1",
            "oidcSub": "sub1",
        }

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps(
                    {
                        "grant_type": "authorization_code",
                        "code": "code",
                        "code_verifier": "wrong",
                        "client_id": "client1",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400


class TestOAuthTokenRefreshToken:
    def test_success_returns_new_access_token(
        self, route, mock_oauth_code_manager, mock_jwt_service, mock_account_manager
    ):
        token = "refresh-token-value"
        mock_oauth_code_manager.consume_refresh_token.return_value = {
            "uid": "uid1",
            "clientId": "client1",
            "scope": "openid",
        }
        mock_jwt_service.sign_jwt.return_value = "new-jwt"
        mock_oauth_code_manager.create_refresh_token.return_value = "new-refresh"
        mock_account_manager.get_account_by_uid.return_value = {
            "uid": "uid1",
            "oidcSub": "oidc-sub-123",
        }

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": token,
                        "client_id": "client1",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["access_token"] == "new-jwt"
        assert body["refresh_token"] == "new-refresh"

    def test_invalid_refresh_token_returns_400(self, route, mock_oauth_code_manager):
        mock_oauth_code_manager.consume_refresh_token.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": "bad",
                        "client_id": "c",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400


class TestOAuthTokenAuthCodeEdgeCases:
    def test_missing_code_returns_400(self, route, mock_oauth_code_manager):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps({"grant_type": "authorization_code", "client_id": "c"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_code_verifier_when_challenge_present_returns_400(
        self, route, mock_oauth_code_manager, mock_account_manager
    ):
        mock_oauth_code_manager.consume_authorization_code.return_value = {
            "uid": "uid1",
            "clientId": "client1",
            "scope": "openid",
            "codeChallenge": "challenge",
            "codeChallengeMethod": "S256",
        }
        mock_account_manager.get_account_by_uid.return_value = {
            "uid": "uid1",
            "oidcSub": "sub1",
        }
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps(
                    {
                        "grant_type": "authorization_code",
                        "code": "code",
                        "client_id": "client1",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_account_not_found_returns_400(
        self, route, mock_oauth_code_manager, mock_account_manager
    ):
        mock_oauth_code_manager.consume_authorization_code.return_value = {
            "uid": "uid1",
            "clientId": "client1",
            "scope": "openid",
            "codeChallenge": "",
            "codeChallengeMethod": "S256",
        }
        mock_account_manager.get_account_by_uid.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps(
                    {
                        "grant_type": "authorization_code",
                        "code": "code",
                        "code_verifier": "v",
                        "client_id": "c",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400


class TestOAuthTokenTTLCap:
    def test_ttl_capped_at_max(
        self, route, mock_oauth_code_manager, mock_jwt_service, mock_account_manager
    ):
        mock_oauth_code_manager.consume_authorization_code.return_value = {
            "uid": "uid1",
            "clientId": "client1",
            "scope": "openid",
            "codeChallenge": "",
            "codeChallengeMethod": "S256",
        }
        mock_jwt_service.sign_jwt.return_value = "jwt"
        mock_oauth_code_manager.create_refresh_token.return_value = "refresh"
        mock_account_manager.get_account_by_uid.return_value = {
            "uid": "uid1",
            "oidcSub": "sub1",
        }

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps(
                    {
                        "grant_type": "authorization_code",
                        "code": "code",
                        "code_verifier": "v",
                        "client_id": "c",
                        "ttl": 9999,
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["expires_in"] == 3600  # MAX_TTL


class TestOAuthTokenScopeValidation:
    def test_refresh_scope_exceeds_grant_returns_400(
        self, route, mock_oauth_code_manager, mock_account_manager
    ):
        mock_oauth_code_manager.consume_refresh_token.return_value = {
            "uid": "uid1",
            "clientId": "client1",
            "scope": "openid",
        }
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": "tok",
                        "client_id": "c",
                        "scope": "openid profile",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert body["errno"] == 165

    def test_refresh_scope_subset_succeeds(
        self, route, mock_oauth_code_manager, mock_jwt_service, mock_account_manager
    ):
        mock_oauth_code_manager.consume_refresh_token.return_value = {
            "uid": "uid1",
            "clientId": "client1",
            "scope": "openid profile",
        }
        mock_jwt_service.sign_jwt.return_value = "jwt"
        mock_oauth_code_manager.create_refresh_token.return_value = "refresh"
        mock_account_manager.get_account_by_uid.return_value = {
            "uid": "uid1",
            "oidcSub": "sub1",
        }
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": "tok",
                        "client_id": "c",
                        "scope": "openid",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200


class TestOAuthTokenRefreshEdgeCases:
    def test_missing_refresh_token_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps({"grant_type": "refresh_token", "client_id": "c"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_account_not_found_on_refresh_returns_400(
        self, route, mock_oauth_code_manager, mock_account_manager
    ):
        mock_oauth_code_manager.consume_refresh_token.return_value = {
            "uid": "uid1",
            "clientId": "client1",
            "scope": "openid",
        }
        mock_account_manager.get_account_by_uid.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": "tok",
                        "client_id": "c",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400


class TestOAuthTokenErrors:
    def test_invalid_json_body_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": "not-json",
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_grant_type_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps({"code": "abc"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_invalid_grant_type_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps({"grant_type": "password"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_missing_body_returns_400(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 400


class TestOAuthTokenFxaCredentials:
    def test_success_returns_access_token(
        self, route, mock_token_manager, mock_jwt_service, mock_account_manager
    ):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        mock_jwt_service.sign_jwt.return_value = "fxa-cred-jwt"
        mock_account_manager.get_account_by_uid.return_value = {
            "uid": "uid1",
            "oidcSub": "sub1",
        }

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": json.dumps(
                    {
                        "grant_type": "fxa-credentials",
                        "client_id": "client1",
                        "scope": "profile",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["access_token"] == "fxa-cred-jwt"
        assert body["token_type"] == "bearer"
        assert body["scope"] == "profile"
        assert "refresh_token" not in body

    def test_missing_auth_returns_401(self, route, mock_token_manager):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {},
                "body": json.dumps(
                    {
                        "grant_type": "fxa-credentials",
                        "client_id": "c",
                        "scope": "profile",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_invalid_session_returns_401(self, route, mock_token_manager):
        mock_token_manager.verify_session_hawk.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {"authorization": 'Hawk id="bad"'},
                "body": json.dumps(
                    {
                        "grant_type": "fxa-credentials",
                        "client_id": "c",
                        "scope": "profile",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_returns_400_when_token_manager_not_configured(
        self, mock_oauth_code_manager, mock_jwt_service, mock_account_manager
    ):
        route_no_tm = OAuthTokenRoute(
            oauth_code_manager=mock_oauth_code_manager,
            jwt_service=mock_jwt_service,
            account_manager=mock_account_manager,
            metrics=MagicMock(),
        )
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": json.dumps(
                    {
                        "grant_type": "fxa-credentials",
                        "client_id": "c",
                        "scope": "profile",
                    }
                ),
            }
        )
        response = route_no_tm.handle(event)
        assert response.status_code == 400

    def test_account_not_found_returns_400(self, route, mock_token_manager, mock_account_manager):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        mock_account_manager.get_account_by_uid.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": json.dumps(
                    {
                        "grant_type": "fxa-credentials",
                        "client_id": "c",
                        "scope": "profile",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400


class TestOAuthTokenBind:
    def test_bind_registers_post_route(self, route):
        mock_api = MagicMock()
        mock_api.post = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.post.assert_called_once_with("/v1/oauth/token")
