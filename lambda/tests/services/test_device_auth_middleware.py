"""Tests for DeviceAuthMiddleware (OAuth refresh token bearer auth on device routes)."""

import hashlib
from typing import Optional
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.event_handler import Response
from botocore.stub import Stubber

from src.middlewares.device_auth import DeviceAuthMiddleware
from src.middlewares.hawk_auth import HawkAuthenticationError
from src.services.oauth_code_manager import OAuthCodeManager
from tests.conftest import json_body


def _make_app(auth_header: Optional[str]) -> MagicMock:
    app = MagicMock()
    headers = {}
    if auth_header is not None:
        headers["Authorization"] = auth_header
    event = MagicMock()
    event.headers = headers
    raw_event: dict = {"requestContext": {}}
    event.__getitem__ = lambda self, key: raw_event[key]
    event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
    app.current_event = event
    return app


class TestDeviceAuthMiddleware:
    def test_bearer_valid_sets_hawk_uid_and_calls_next(
        self,
        dynamodb_table: object,
        dynamodb_stubber: Stubber,
    ) -> None:
        token = "abcdef1234"
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        oauth = OAuthCodeManager(table=dynamodb_table)
        session_hawk = MagicMock()
        middleware = DeviceAuthMiddleware(
            metrics=MagicMock(), oauth_code_manager=oauth, session_hawk=session_hawk
        )

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"REFRESH#{token_hash}"},
                    "uid": {"S": "uid1"},
                    "clientId": {"S": "client1"},
                    "scope": {"S": "openid"},
                    "expiry": {"N": "9999999999"},
                }
            },
        )

        app = _make_app(f"Bearer {token}")
        next_mw = MagicMock(return_value=Response(status_code=200, body='{"ok": true}'))

        result = middleware.handler(app, next_mw)

        assert app.current_event["requestContext"]["hawk_uid"] == "uid1"
        assert "hawk_token_id" not in app.current_event["requestContext"]
        next_mw.assert_called_once_with(app)
        session_hawk.handler.assert_not_called()
        assert json_body(result) == {"ok": True}

    def test_bearer_unknown_raises(
        self,
        dynamodb_table: object,
        dynamodb_stubber: Stubber,
    ) -> None:
        oauth = OAuthCodeManager(table=dynamodb_table)
        session_hawk = MagicMock()
        middleware = DeviceAuthMiddleware(
            metrics=MagicMock(), oauth_code_manager=oauth, session_hawk=session_hawk
        )

        dynamodb_stubber.add_response("get_item", {})

        with pytest.raises(HawkAuthenticationError):
            middleware.handler(_make_app("Bearer unknown"), MagicMock())

        session_hawk.handler.assert_not_called()

    def test_non_bearer_delegates_to_session_hawk(
        self,
        dynamodb_table: object,
        dynamodb_stubber: Stubber,
    ) -> None:
        oauth = OAuthCodeManager(table=dynamodb_table)
        session_hawk = MagicMock()
        response = Response(status_code=200, body="{}")
        session_hawk.handler.return_value = response
        middleware = DeviceAuthMiddleware(
            metrics=MagicMock(), oauth_code_manager=oauth, session_hawk=session_hawk
        )

        app = _make_app('Hawk id="tokenid"')
        next_mw = MagicMock()

        result = middleware.handler(app, next_mw)

        session_hawk.handler.assert_called_once_with(app, next_mw)
        assert result is response

    def test_missing_header_delegates_to_session_hawk(
        self,
        dynamodb_table: object,
        dynamodb_stubber: Stubber,
    ) -> None:
        oauth = OAuthCodeManager(table=dynamodb_table)
        session_hawk = MagicMock()
        session_hawk.handler.side_effect = HawkAuthenticationError(
            "Missing or invalid authorization"
        )
        middleware = DeviceAuthMiddleware(
            metrics=MagicMock(), oauth_code_manager=oauth, session_hawk=session_hawk
        )

        with pytest.raises(HawkAuthenticationError):
            middleware.handler(_make_app(None), MagicMock())

        session_hawk.handler.assert_called_once()
