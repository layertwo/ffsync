"""Integration-level tests that verify routes work via ApiRouter dispatch.

These tests exercise the bind() closure bodies which unit tests call directly via handle().
"""

from unittest.mock import MagicMock

from src.routes.auth.account_create import AccountCreateRoute
from src.routes.auth.account_keys import AccountKeysRoute
from src.routes.auth.account_login import AccountLoginRoute
from src.routes.auth.account_profile import AccountProfileRoute
from src.routes.auth.account_status import AccountStatusRoute
from src.routes.auth.jwks import JWKSRoute
from src.routes.auth.oauth_authorization import OAuthAuthorizationRoute
from src.routes.auth.oauth_destroy import OAuthDestroyRoute
from src.routes.auth.oauth_token import OAuthTokenRoute
from src.routes.auth.oidc_discovery import OIDCDiscoveryRoute
from src.routes.auth.oidc_exchange import OIDCCodeExchangeRoute, OIDCProviderConfigRoute
from src.routes.auth.scoped_key_data import ScopedKeyDataRoute
from src.routes.auth.session_destroy import SessionDestroyRoute
from src.routes.auth.session_status import SessionStatusRoute
from src.services.api_router import ApiRouter


def _make_event(method, path, headers=None, body=None, qs=None):
    return {
        "httpMethod": method,
        "path": path,
        "headers": headers or {},
        "body": body,
        "queryStringParameters": qs,
        "requestContext": {"requestId": "test"},
    }


def _make_context():
    ctx = MagicMock()
    ctx.function_name = "test"
    return ctx


def _router(route):
    return ApiRouter(routes=[route], middlewares=[])


class TestRouteDispatch:
    """Verify each route's bind closure is exercised via ApiRouter."""

    def test_account_status_dispatches(self):
        mgr = MagicMock()
        mgr.get_account_by_email.return_value = None
        router = _router(AccountStatusRoute(account_manager=mgr))
        result = router.handler(
            _make_event("GET", "/v1/account/status", qs={"email": "a@b.com"}), _make_context()
        )
        assert result["statusCode"] == 200

    def test_account_create_dispatches(self):
        route = AccountCreateRoute(
            account_manager=MagicMock(), token_manager=MagicMock(), oidc_validator=MagicMock()
        )
        result = _router(route).handler(
            _make_event("POST", "/v1/account/create", body="{}"), _make_context()
        )
        assert result["statusCode"] == 401

    def test_account_login_dispatches(self):
        route = AccountLoginRoute(account_manager=MagicMock(), token_manager=MagicMock())
        result = _router(route).handler(
            _make_event("POST", "/v1/account/login", body="{}"), _make_context()
        )
        assert result["statusCode"] == 400

    def test_account_keys_dispatches(self):
        route = AccountKeysRoute(account_manager=MagicMock(), token_manager=MagicMock())
        result = _router(route).handler(_make_event("GET", "/v1/account/keys"), _make_context())
        assert result["statusCode"] == 401

    def test_account_profile_dispatches(self):
        route = AccountProfileRoute(account_manager=MagicMock(), token_manager=MagicMock())
        result = _router(route).handler(_make_event("GET", "/v1/account/profile"), _make_context())
        assert result["statusCode"] == 401

    def test_scoped_key_data_dispatches(self):
        route = ScopedKeyDataRoute(account_manager=MagicMock(), token_manager=MagicMock())
        result = _router(route).handler(
            _make_event("POST", "/v1/account/scoped-key-data", body="{}"), _make_context()
        )
        assert result["statusCode"] == 401

    def test_session_status_dispatches(self):
        route = SessionStatusRoute(token_manager=MagicMock())
        result = _router(route).handler(_make_event("GET", "/v1/session/status"), _make_context())
        assert result["statusCode"] == 401

    def test_session_destroy_dispatches(self):
        route = SessionDestroyRoute(token_manager=MagicMock())
        result = _router(route).handler(_make_event("POST", "/v1/session/destroy"), _make_context())
        assert result["statusCode"] == 401

    def test_oauth_authorization_dispatches(self):
        route = OAuthAuthorizationRoute(token_manager=MagicMock(), oauth_code_manager=MagicMock())
        result = _router(route).handler(
            _make_event("POST", "/v1/oauth/authorization", body="{}"), _make_context()
        )
        assert result["statusCode"] == 401

    def test_oauth_token_dispatches(self):
        route = OAuthTokenRoute(
            oauth_code_manager=MagicMock(), jwt_service=MagicMock(), account_manager=MagicMock()
        )
        result = _router(route).handler(
            _make_event("POST", "/v1/oauth/token", body="{}"), _make_context()
        )
        assert result["statusCode"] == 400

    def test_oauth_destroy_dispatches(self):
        route = OAuthDestroyRoute(oauth_code_manager=MagicMock())
        result = _router(route).handler(
            _make_event("POST", "/v1/oauth/destroy", body="{}"), _make_context()
        )
        assert result["statusCode"] in (200, 400)

    def test_oidc_discovery_dispatches(self):
        jwt_svc = MagicMock()
        jwt_svc.issuer = "https://auth.example.com"
        route = OIDCDiscoveryRoute(jwt_service=jwt_svc)
        result = _router(route).handler(
            _make_event("GET", "/.well-known/openid-configuration"), _make_context()
        )
        assert result["statusCode"] == 200

    def test_jwks_dispatches(self):
        jwt_svc = MagicMock()
        jwt_svc.get_public_key_jwk.return_value = {"kty": "RSA", "kid": "test"}
        route = JWKSRoute(jwt_service=jwt_svc)
        result = _router(route).handler(_make_event("GET", "/v1/jwks"), _make_context())
        assert result["statusCode"] == 200

    def test_oidc_provider_config_dispatches(self):
        validator = MagicMock()
        validator.discover_provider_config.return_value = MagicMock(
            authorization_endpoint="https://idp.example.com/authorize"
        )
        route = OIDCProviderConfigRoute(oidc_validator=validator)
        result = _router(route).handler(_make_event("GET", "/v1/oidc/config"), _make_context())
        assert result["statusCode"] == 200

    def test_oidc_code_exchange_dispatches(self):
        route = OIDCCodeExchangeRoute(oidc_validator=MagicMock(), account_manager=MagicMock())
        result = _router(route).handler(
            _make_event("POST", "/v1/oidc/exchange", body="{}"), _make_context()
        )
        assert result["statusCode"] == 400
