"""Firefox Accounts profile-server conformance for GET /v1/profile.

FxA's profile server returns a JSON object whose fields are all nullable
(``packages/fxa-profile-server/lib/routes/profile.js``):

    email, additionalEmails, uid, avatar, avatarDefault, displayName, locale,
    amrValues, twoFactorAuthentication, subscriptions, metricsEnabled, sub, ...

Firefox reads ``email``/``locale`` (and ``displayName``/``avatar`` for the
account panel). The endpoint is OAuth-Bearer authenticated with the ``profile``
scope.

Fields this service does not return are pinned with ``xfail(strict=True)`` so the
gap is recorded rather than assumed absent.
"""

from typing import Optional
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.event_handler import Response
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.profile.get_profile import GetProfileRoute
from src.shared.oidc import OIDCTokenClaims
from tests.conftest import json_body

ACCOUNT = {"uid": "uid-123", "email": "user@example.com", "oidcSub": "oidc-sub-123"}


@pytest.fixture
def verifier() -> MagicMock:
    verifier = MagicMock()
    verifier.validate_token.return_value = OIDCTokenClaims(
        sub="oidc-sub-123",
        iss="https://auth.example.com",
        aud="client-id",
        exp=9999999999,
        iat=1000000000,
        scope="profile",
    )
    return verifier


@pytest.fixture
def accounts() -> MagicMock:
    accounts = MagicMock()
    accounts.get_account_by_oidc_sub.return_value = ACCOUNT
    accounts.get_account_by_uid.return_value = None
    return accounts


@pytest.fixture
def route(verifier: MagicMock, accounts: MagicMock) -> GetProfileRoute:
    return GetProfileRoute(
        jwt_verifier=verifier, auth_account_manager=accounts, metrics=MagicMock()
    )


def _get(route: GetProfileRoute, authorization: Optional[str] = "Bearer a.b.c") -> Response:
    headers = {} if authorization is None else {"authorization": authorization}
    return route.handle(
        APIGatewayProxyEvent({"httpMethod": "GET", "path": "/v1/profile", "headers": headers})
    )


class TestProfileResponse:
    def test_returns_uid_email_and_locale(self, route: GetProfileRoute) -> None:
        """The three fields Firefox actually reads."""
        response = _get(route)

        assert response.status_code == 200
        body = json_body(response)
        assert body["uid"] == "uid-123"
        assert body["email"] == "user@example.com"
        assert body["locale"]

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "FxA's profile schema includes amrValues (array, nullable) -- the authentication "
            "methods used, e.g. ['pwd','otp']. FireFox shows it in the account panel; we never "
            "return it."
        ),
    )
    def test_returns_amr_values(self, route: GetProfileRoute) -> None:
        assert "amrValues" in json_body(_get(route))

    def test_returns_two_factor_authentication(self, route: GetProfileRoute) -> None:
        # FxA reports the account's 2FA state (its schema allows null when it cannot
        # tell); this service has no second factor, so false is accurate.
        assert json_body(_get(route))["twoFactorAuthentication"] is False


class TestProfileAuth:
    def test_missing_authorization_is_rejected(self, route: GetProfileRoute) -> None:
        response = _get(route, authorization=None)

        assert response.status_code == 401
        assert json_body(response)["errno"] == 110

    def test_non_bearer_authorization_is_rejected(self, route: GetProfileRoute) -> None:
        response = _get(route, authorization="Hawk id=1")

        assert response.status_code == 401

    def test_invalid_token_is_rejected(self, route: GetProfileRoute, verifier: MagicMock) -> None:
        from src.shared.exceptions import InvalidTokenError

        verifier.validate_token.side_effect = InvalidTokenError("bad signature")

        assert _get(route).status_code == 401

    @pytest.mark.parametrize(
        "scope", [None, "", "oldsync", "https://identity.mozilla.com/apps/oldsync"]
    )
    def test_token_without_the_profile_scope_is_rejected(
        self, route: GetProfileRoute, verifier: MagicMock, scope: Optional[str]
    ) -> None:
        """RFC 6750: a valid token lacking the needed scope is 403, not 401."""
        verifier.validate_token.return_value = OIDCTokenClaims(
            sub="oidc-sub-123",
            iss="https://auth.example.com",
            aud="client-id",
            exp=9999999999,
            iat=1000000000,
            scope=scope,
        )

        response = _get(route)

        assert response.status_code == 403
        assert json_body(response)["errno"] == 111
