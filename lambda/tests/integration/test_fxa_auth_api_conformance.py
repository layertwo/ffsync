"""Firefox Accounts auth-server conformance for the Auth API.

Spec sources, all read from mozilla/fxa:

* The errno registry, and the HTTP status each errno maps to, lives in
  ``libs/accounts/errors/src/constants.ts`` (ERRNO) and
  ``libs/accounts/errors/src/app-error.ts`` (one factory per errno, each with an
  explicit ``code``). The same table is published in
  ``packages/fxa-auth-server/docs/swagger/auth-server-api.ts``.
* Payload validation: ``AppError.translate`` maps a hapi validation failure
  whose message contains ``is required`` to errno 108 (missing parameter) and
  every other validation failure to errno 107 (invalid parameter).
* The OAuth routes throw ``OauthError`` errnos, which
  ``AppError.appErrorFromOauthError`` translates back into the table above --
  OauthError 105 (unknown code) -> 172, 106 (mismatch) -> 173, 107 (expired) ->
  174, 108 (invalid token) -> 110, 117 (bad PKCE challenge) -> 175, 118
  (missing PKCE parameters) -> 169, 122 (unknown token) -> 182.
* PKCE: ``lib/routes/oauth/authorization.js`` requires it for public clients and
  rejects it for confidential ones; that needs a client registry we do not have.

A missing ``error``/``info`` key on our error bodies is a cosmetic difference
only: Firefox reads every field with ``unwrap_or`` in
``components/fxa-client/src/internal/http_client.rs``. It is not pinned here.

Deviations are pinned with ``xfail(strict=True)`` so that fixing one flips a
single marker instead of requiring a new test. The errno set below is now
implemented; the only remaining pin is PKCE enforcement, which is blocked on an
OAuth client registry (public and confidential clients need opposite answers).
"""

import json
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.event_handler import Response
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.environment.service_provider import ServiceProvider
from src.routes.auth.account_attached_clients import AccountAttachedClientsRoute
from src.routes.auth.account_create import AccountCreateRoute
from src.routes.auth.account_devices import AccountDevicesRoute
from src.routes.auth.account_keys import AccountKeysRoute
from src.routes.auth.account_login import AccountLoginRoute
from src.routes.auth.account_status import AccountStatusRoute
from src.routes.auth.oauth_authorization import OAuthAuthorizationRoute
from src.routes.auth.oauth_destroy import OAuthDestroyRoute
from src.routes.auth.oauth_token import OAuthTokenRoute
from src.routes.auth.scoped_key_data import ScopedKeyDataRoute
from src.routes.auth.session_destroy import SessionDestroyRoute
from src.routes.auth.session_status import SessionStatusRoute
from src.services.fxa_crypto import derive_verify_hash
from src.services.oauth_code_manager import ExpiredAuthorizationCode
from src.shared.oidc import OIDCTokenClaims
from tests.conftest import json_body

UID = "0123456789abcdef0123456789abcdef"
EMAIL = "user@example.com"
AUTH_PW = "ab" * 32  # 64 hex chars, as the client derives it
OTHER_PW = "cd" * 32
SESSION_TOKEN_HEX = "a1" * 32
SESSION_CONTEXT = {"hawk_uid": UID, "hawk_token_id": SESSION_TOKEN_HEX}


def _call(
    route: Any,
    method: str,
    path: str,
    body: Optional[Any] = None,
    headers: Optional[dict[str, str]] = None,
    request_context: Optional[dict[str, Any]] = None,
    query: Optional[dict[str, str]] = None,
) -> Response[Any]:
    """Drive a route the way API Gateway would, with the middleware's additions."""
    event: dict[str, Any] = {"httpMethod": method, "path": path}
    if body is not None:
        event["body"] = body if isinstance(body, str) else json.dumps(body)
    if headers is not None:
        event["headers"] = headers
    if request_context is not None:
        event["requestContext"] = request_context
    if query is not None:
        event["queryStringParameters"] = query
    return route.handle(APIGatewayProxyEvent(event))


def _registered(provider: ServiceProvider) -> set[tuple[str, str]]:
    """Every (method, path) the auth router serves.

    Powertools keeps literal paths in ``_static_routes`` and parameterised ones
    in ``_dynamic_routes``; both must be read or the guard passes against a
    subset.
    """
    app = provider.auth_api_router.app
    return {(route.method, route.path) for route in [*app._static_routes, *app._dynamic_routes]}


def test_route_table_serves_every_documented_endpoint(
    mock_service_provider: ServiceProvider,
) -> None:
    """Guard: a renamed or dropped endpoint fails here rather than in Firefox."""
    expected = {
        ("GET", "/v1/account/status"),
        ("POST", "/v1/account/create"),
        ("POST", "/v1/account/login"),
        ("GET", "/v1/account/keys"),
        ("POST", "/v1/account/scoped-key-data"),
        ("POST", "/v1/account/device"),
        ("GET", "/v1/account/devices"),
        ("GET", "/v1/account/attached_clients"),
        ("POST", "/v1/account/devices/notify"),
        ("GET", "/v1/session/status"),
        ("POST", "/v1/session/destroy"),
        ("POST", "/v1/oauth/authorization"),
        ("POST", "/v1/oauth/token"),
        ("POST", "/v1/oauth/destroy"),
        ("GET", "/.well-known/openid-configuration"),
        ("GET", "/v1/jwks"),
        ("GET", "/v1/oidc/config"),
        ("POST", "/v1/oidc/exchange"),
    }

    registered = _registered(mock_service_provider)

    assert registered == expected, f"route table drift: {registered ^ expected}"


class TestErrorEnvelope:
    def test_error_bodies_are_code_errno_message(self) -> None:
        route = AccountStatusRoute(account_manager=MagicMock())

        response = _call(route, "GET", "/v1/account/status")
        body = json_body(response)

        assert response.status_code == 400
        assert set(body) == {"code", "errno", "message"}
        assert body["code"] == response.status_code


@pytest.fixture
def accounts() -> MagicMock:
    accounts = MagicMock()
    accounts.get_account_by_email.return_value = {
        "uid": UID,
        "verifyHash": derive_verify_hash(bytes.fromhex(AUTH_PW)).hex(),
        "oidcSub": "oidc-sub",
    }
    return accounts


@pytest.fixture
def tokens() -> MagicMock:
    tokens = MagicMock()
    tokens.create_session_token.return_value = b"\x01" * 32
    tokens.create_key_fetch_token.return_value = b"\x02" * 32
    return tokens


@pytest.fixture
def login(accounts: MagicMock, tokens: MagicMock) -> AccountLoginRoute:
    return AccountLoginRoute(account_manager=accounts, token_manager=tokens)


class TestAccountLogin:
    def test_success_returns_uid_session_token_and_verified(self, login: AccountLoginRoute) -> None:
        response = _call(
            login, "POST", "/v1/account/login", body={"email": EMAIL, "authPW": AUTH_PW}
        )

        assert response.status_code == 200
        body = json_body(response)
        assert body["uid"] == UID
        assert body["sessionToken"] == (b"\x01" * 32).hex()
        assert body["verified"] is True

    def test_unknown_account_is_400_102(
        self, login: AccountLoginRoute, accounts: MagicMock
    ) -> None:
        accounts.get_account_by_email.return_value = None

        response = _call(
            login, "POST", "/v1/account/login", body={"email": EMAIL, "authPW": AUTH_PW}
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 102

    def test_incorrect_password_is_400_103(self, login: AccountLoginRoute) -> None:
        response = _call(
            login, "POST", "/v1/account/login", body={"email": EMAIL, "authPW": OTHER_PW}
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 103

    def test_malformed_email_is_400_107(self, login: AccountLoginRoute) -> None:
        """A failed format check is an invalid parameter (107), not a missing one."""
        response = _call(
            login, "POST", "/v1/account/login", body={"email": "not-an-email", "authPW": AUTH_PW}
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 107

    def test_invalid_json_is_400_106(self, login: AccountLoginRoute) -> None:
        response = _call(login, "POST", "/v1/account/login", body="{not json")

        assert response.status_code == 400
        assert json_body(response)["errno"] == 106

    def test_missing_email_is_400_108(self, login: AccountLoginRoute) -> None:
        response = _call(login, "POST", "/v1/account/login", body={"authPW": AUTH_PW})

        assert response.status_code == 400
        assert json_body(response)["errno"] == 108

    def test_missing_auth_pw_is_400_108(self, login: AccountLoginRoute) -> None:
        response = _call(login, "POST", "/v1/account/login", body={"email": EMAIL})

        assert response.status_code == 400
        assert json_body(response)["errno"] == 108


class TestAccountStatus:
    @pytest.fixture
    def status(self) -> tuple[AccountStatusRoute, MagicMock]:
        accounts = MagicMock()
        accounts.get_account_by_email.return_value = {"uid": UID}
        return AccountStatusRoute(account_manager=accounts), accounts

    def test_existing_account_reports_exists_true(
        self, status: tuple[AccountStatusRoute, MagicMock]
    ) -> None:
        route, _ = status

        response = _call(route, "GET", "/v1/account/status", query={"email": EMAIL})

        assert response.status_code == 200
        assert json_body(response)["exists"] is True

    def test_unknown_account_reports_exists_false(
        self, status: tuple[AccountStatusRoute, MagicMock]
    ) -> None:
        route, accounts = status
        accounts.get_account_by_email.return_value = None

        response = _call(route, "GET", "/v1/account/status", query={"email": EMAIL})

        assert response.status_code == 200
        assert json_body(response)["exists"] is False

    def test_missing_email_is_400_108(self, status: tuple[AccountStatusRoute, MagicMock]) -> None:
        route, _ = status

        response = _call(route, "GET", "/v1/account/status")

        assert response.status_code == 400
        assert json_body(response)["errno"] == 108


def _create_route() -> tuple[AccountCreateRoute, MagicMock, MagicMock]:
    accounts = MagicMock()
    tokens = MagicMock()
    tokens.create_session_token.return_value = b"\x03" * 32
    tokens.create_key_fetch_token.return_value = b"\x04" * 32
    validator = MagicMock()
    validator.validate_token.return_value = OIDCTokenClaims(
        sub="oidc-sub",
        iss="https://auth.example.com",
        aud="client-id",
        exp=9999999999,
        iat=1000000000,
    )
    route = AccountCreateRoute(
        account_manager=accounts, token_manager=tokens, oidc_validator=validator
    )
    return route, accounts, tokens


class TestAccountCreate:
    def test_success_returns_both_tokens(self) -> None:
        route, _, _ = _create_route()

        response = _call(
            route,
            "POST",
            "/v1/account/create",
            body={"email": EMAIL, "authPW": AUTH_PW},
            headers={"authorization": "Bearer oidc-token"},
        )

        assert response.status_code == 200
        body = json_body(response)
        assert body["uid"]
        assert body["sessionToken"] == (b"\x03" * 32).hex()
        assert body["keyFetchToken"] == (b"\x04" * 32).hex()

    def test_missing_bearer_is_401_110(self) -> None:
        route, _, _ = _create_route()

        response = _call(
            route, "POST", "/v1/account/create", body={"email": EMAIL, "authPW": AUTH_PW}
        )

        assert response.status_code == 401
        assert json_body(response)["errno"] == 110

    def test_duplicate_account_is_400_101(self) -> None:
        route, accounts, _ = _create_route()
        accounts.create_account.side_effect = ValueError("Account already exists")

        response = _call(
            route,
            "POST",
            "/v1/account/create",
            body={"email": EMAIL, "authPW": AUTH_PW},
            headers={"authorization": "Bearer oidc-token"},
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 101


class TestSessionRoutes:
    def test_status_returns_state_and_uid(self) -> None:
        route = SessionStatusRoute()

        response = _call(route, "GET", "/v1/session/status", request_context=dict(SESSION_CONTEXT))

        assert response.status_code == 200
        body = json_body(response)
        assert body["state"] == "verified"
        assert body["uid"] == UID

    def test_destroy_deletes_the_session_and_returns_an_empty_object(self) -> None:
        tokens = MagicMock()
        tokens.extract_token_id_from_hawk_header.return_value = "aabbcc"
        route = SessionDestroyRoute(token_manager=tokens)

        response = _call(
            route,
            "POST",
            "/v1/session/destroy",
            headers={"authorization": "Hawk id=aabbcc, ts=1, nonce=2, mac=3"},
            request_context=dict(SESSION_CONTEXT),
        )

        assert response.status_code == 200
        assert json_body(response) == {}
        tokens.delete_session.assert_called_once_with("aabbcc")


class TestScopedKeyData:
    def test_response_is_keyed_by_scope_with_the_documented_fields(self) -> None:
        scope = "https://identity.mozilla.com/apps/oldsync"
        accounts = MagicMock()
        accounts.get_account_by_uid.return_value = {
            "uid": UID,
            "createdAt": 1700000000,
            "keyRotationSecret": "11" * 32,
        }
        route = ScopedKeyDataRoute(account_manager=accounts)

        response = _call(
            route,
            "POST",
            "/v1/account/scoped-key-data",
            body={"client_id": "client-id", "scope": scope},
            request_context=dict(SESSION_CONTEXT),
        )

        assert response.status_code == 200
        body = json_body(response)
        assert set(body) == {scope}
        assert body[scope]["identifier"] == scope
        assert body[scope]["keyRotationSecret"] == "11" * 32
        # FxA currently sends a placeholder rotation timestamp (0); only its
        # presence and type are part of the contract.
        assert isinstance(body[scope]["keyRotationTimestamp"], int)

    def test_missing_scope_is_400_108(self) -> None:
        """client_id and scope are both required; FxA answers 108 for either."""
        route = ScopedKeyDataRoute(account_manager=MagicMock())

        response = _call(
            route,
            "POST",
            "/v1/account/scoped-key-data",
            body={"client_id": "client-id"},
            request_context=dict(SESSION_CONTEXT),
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 108


@pytest.fixture
def authorization() -> OAuthAuthorizationRoute:
    codes = MagicMock()
    codes.create_authorization_code.return_value = "auth-code"
    return OAuthAuthorizationRoute(oauth_code_manager=codes)


class TestOAuthAuthorization:
    def test_returns_code_state_and_redirect(self, authorization: OAuthAuthorizationRoute) -> None:
        response = _call(
            authorization,
            "POST",
            "/v1/oauth/authorization",
            body={"client_id": "client-id", "scope": "profile", "state": "state-1"},
            request_context=dict(SESSION_CONTEXT),
        )

        assert response.status_code == 200
        assert json_body(response) == {
            "code": "auth-code",
            "state": "state-1",
            "redirect": "urn:ietf:wg:oauth:2.0:oob",
        }

    def test_unknown_redirect_uri_is_400_167(self, authorization: OAuthAuthorizationRoute) -> None:
        response = _call(
            authorization,
            "POST",
            "/v1/oauth/authorization",
            body={
                "client_id": "client-id",
                "scope": "profile",
                "state": "state-1",
                "redirect_uri": "https://attacker.example.com/callback",
            },
            request_context=dict(SESSION_CONTEXT),
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 167

    def test_missing_client_id_is_400_108(self, authorization: OAuthAuthorizationRoute) -> None:
        response = _call(
            authorization,
            "POST",
            "/v1/oauth/authorization",
            body={"scope": "profile", "state": "state-1"},
            request_context=dict(SESSION_CONTEXT),
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 108

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "FxA requires PKCE for public clients (errno 169) and rejects it for confidential "
            "ones (errno 166); we cannot tell them apart, as there is no OAuth client registry, "
            "so an authorization request with no code_challenge is accepted."
        ),
    )
    def test_missing_code_challenge_is_rejected(
        self, authorization: OAuthAuthorizationRoute
    ) -> None:
        response = _call(
            authorization,
            "POST",
            "/v1/oauth/authorization",
            body={"client_id": "client-id", "scope": "profile", "state": "state-1"},
            request_context=dict(SESSION_CONTEXT),
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 169


def _token_route() -> tuple[OAuthTokenRoute, MagicMock, MagicMock]:
    codes = MagicMock()
    accounts = MagicMock()
    accounts.get_account_by_uid.return_value = {"uid": UID, "oidcSub": "oidc-sub"}
    jwt = MagicMock()
    jwt.sign_jwt.return_value = "signed.jwt.token"
    route = OAuthTokenRoute(
        oauth_code_manager=codes,
        jwt_service=jwt,
        account_manager=accounts,
        metrics=MagicMock(),
    )
    return route, codes, jwt


class TestOAuthToken:
    def test_authorization_code_grant_returns_the_documented_fields(self) -> None:
        route, codes, _ = _token_route()
        codes.consume_authorization_code.return_value = {
            "uid": UID,
            "scope": "profile",
            "clientId": "client-id",
            "codeChallenge": "",
            "codeChallengeMethod": "S256",
            "keysJwe": "",
        }
        codes.create_refresh_token.return_value = "refresh-token"

        response = _call(
            route,
            "POST",
            "/v1/oauth/token",
            body={"grant_type": "authorization_code", "code": "auth-code"},
        )

        assert response.status_code == 200
        body = json_body(response)
        assert body["access_token"] == "signed.jwt.token"
        assert body["token_type"] == "bearer"
        assert body["scope"] == "profile"
        assert body["refresh_token"] == "refresh-token"
        assert {"expires_in", "auth_at"} <= set(body)

    def test_expires_in_is_capped_at_one_hour(self) -> None:
        route, codes, _ = _token_route()
        codes.consume_authorization_code.return_value = {
            "uid": UID,
            "scope": "profile",
            "clientId": "client-id",
            "codeChallenge": "",
            "codeChallengeMethod": "S256",
            "keysJwe": "",
        }
        codes.create_refresh_token.return_value = "refresh-token"

        response = _call(
            route,
            "POST",
            "/v1/oauth/token",
            body={"grant_type": "authorization_code", "code": "auth-code", "ttl": 99999},
        )

        assert json_body(response)["expires_in"] == 3600

    def test_refresh_token_grant_issues_a_new_refresh_token(self) -> None:
        route, codes, _ = _token_route()
        codes.consume_refresh_token.return_value = {
            "uid": UID,
            "scope": "profile",
            "clientId": "client-id",
        }
        codes.create_refresh_token.return_value = "rotated-refresh-token"

        response = _call(
            route,
            "POST",
            "/v1/oauth/token",
            body={"grant_type": "refresh_token", "refresh_token": "refresh-token"},
        )

        assert response.status_code == 200
        assert json_body(response)["refresh_token"] == "rotated-refresh-token"

    def test_unknown_authorization_code_is_400_172(self) -> None:
        route, codes, _ = _token_route()
        codes.consume_authorization_code.return_value = None

        response = _call(
            route,
            "POST",
            "/v1/oauth/token",
            body={"grant_type": "authorization_code", "code": "no-such-code"},
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 172

    def test_expired_authorization_code_is_400_174(self) -> None:
        route, codes, _ = _token_route()
        codes.consume_authorization_code.side_effect = ExpiredAuthorizationCode("auth-code")

        response = _call(
            route,
            "POST",
            "/v1/oauth/token",
            body={"grant_type": "authorization_code", "code": "stale-code"},
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 174

    def test_bad_code_verifier_is_400_175(self) -> None:
        route, codes, _ = _token_route()
        codes.consume_authorization_code.return_value = {
            "uid": UID,
            "scope": "profile",
            "clientId": "client-id",
            "codeChallenge": "A" * 43,
            "codeChallengeMethod": "S256",
            "keysJwe": "",
        }

        response = _call(
            route,
            "POST",
            "/v1/oauth/token",
            body={
                "grant_type": "authorization_code",
                "code": "auth-code",
                "code_verifier": "B" * 43,
            },
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 175

    def test_missing_code_verifier_for_a_pkce_code_is_400_169(self) -> None:
        """FxA answers 169 (MISSING_PKCE_PARAMETERS), not 108, for this case."""
        route, codes, _ = _token_route()
        codes.consume_authorization_code.return_value = {
            "uid": UID,
            "scope": "profile",
            "clientId": "client-id",
            "codeChallenge": "A" * 43,
            "codeChallengeMethod": "S256",
            "keysJwe": "",
        }

        response = _call(
            route,
            "POST",
            "/v1/oauth/token",
            body={"grant_type": "authorization_code", "code": "auth-code"},
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 169

    def test_unknown_refresh_token_is_400_182(self) -> None:
        route, codes, _ = _token_route()
        codes.consume_refresh_token.return_value = None

        response = _call(
            route,
            "POST",
            "/v1/oauth/token",
            body={"grant_type": "refresh_token", "refresh_token": "no-such-token"},
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 182

    def test_scope_escalation_is_400_163(self) -> None:
        route, codes, _ = _token_route()
        codes.consume_refresh_token.return_value = {
            "uid": UID,
            "scope": "profile",
            "clientId": "client-id",
        }

        response = _call(
            route,
            "POST",
            "/v1/oauth/token",
            body={
                "grant_type": "refresh_token",
                "refresh_token": "refresh-token",
                "scope": "profile https://identity.mozilla.com/apps/oldsync",
            },
        )

        assert response.status_code == 400
        assert json_body(response)["errno"] == 163


class TestAccountKeys:
    def test_missing_authorization_is_401_110(self) -> None:
        route = AccountKeysRoute(account_manager=MagicMock(), token_manager=MagicMock())

        response = _call(route, "GET", "/v1/account/keys")

        assert response.status_code == 401
        assert json_body(response)["errno"] == 110

    def test_bundle_is_the_96_byte_shape_the_client_decrypts(self) -> None:
        tokens = MagicMock()
        tokens.verify_keyfetch_hawk.return_value = {"uid": UID, "keyFetchToken": "00" * 32}
        accounts = MagicMock()
        accounts.get_account_by_uid.return_value = {"kA": "11" * 32, "wrapKB": "22" * 32}
        route = AccountKeysRoute(account_manager=accounts, token_manager=tokens)

        response = _call(
            route,
            "GET",
            "/v1/account/keys",
            headers={"authorization": "Hawk id=1, ts=2, nonce=3, mac=4"},
        )

        assert response.status_code == 200
        assert len(bytes.fromhex(json_body(response)["bundle"])) == 96


class TestDeviceLists:
    def test_devices_is_a_bare_array(self) -> None:
        devices = MagicMock()
        devices.get_devices.return_value = [
            {"id": "device-1", "name": "Firefox", "type": "desktop", "sessionTokenId": "x"}
        ]
        route = AccountDevicesRoute(device_manager=devices)

        response = _call(route, "GET", "/v1/account/devices", request_context=dict(SESSION_CONTEXT))

        assert response.status_code == 200
        body = json_body(response)
        assert isinstance(body, list)
        assert body[0]["id"] == "device-1"

    def test_attached_clients_is_a_bare_array(self) -> None:
        devices = MagicMock()
        devices.get_devices.return_value = [
            {"id": "device-1", "name": "Firefox", "type": "desktop", "sessionTokenId": "x"}
        ]
        route = AccountAttachedClientsRoute(device_manager=devices)

        response = _call(
            route, "GET", "/v1/account/attached_clients", request_context=dict(SESSION_CONTEXT)
        )

        assert response.status_code == 200
        assert isinstance(json_body(response), list)


class TestOAuthDestroy:
    def test_unknown_token_still_returns_200(self) -> None:
        """RFC 7009: revocation is idempotent and does not reveal existence."""
        route = OAuthDestroyRoute(oauth_code_manager=MagicMock())

        response = _call(route, "POST", "/v1/oauth/destroy", body={"token": "no-such-token"})

        assert response.status_code == 200
        assert json_body(response) == {}

    def test_invalid_json_is_400_106(self) -> None:
        route = OAuthDestroyRoute(oauth_code_manager=MagicMock())

        response = _call(route, "POST", "/v1/oauth/destroy", body="{not json")

        assert response.status_code == 400
        assert json_body(response)["errno"] == 106

    def test_missing_token_is_400_108(self) -> None:
        route = OAuthDestroyRoute(oauth_code_manager=MagicMock())

        response = _call(route, "POST", "/v1/oauth/destroy", body={"client_id": "client-id"})

        assert response.status_code == 400
        assert json_body(response)["errno"] == 108
