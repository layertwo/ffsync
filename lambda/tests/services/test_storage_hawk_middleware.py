"""Tests for HawkAuthMiddleware (storage mode)"""

from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.event_handler import Response

from src.middlewares.hawk_auth import HawkAuthenticationError, HawkAuthMiddleware
from src.services.hawk_service import HawkCredentials


def _make_app(
    auth_header=None,
    method="GET",
    path="/1.5/123/storage/bookmarks",
    query_params=None,
    domain_name="storage.example.com",
    path_params=None,
):
    """Build a mock APIGatewayRestResolver app with current_event."""
    app = MagicMock()
    headers = {}
    if auth_header is not None:
        headers["Authorization"] = auth_header
    event = MagicMock()
    event.headers = headers
    event.http_method = method
    event.path = path
    event.query_string_parameters = query_params
    event.request_context.domain_name = domain_name
    # Support dict-style access for event["requestContext"] injection
    request_context: dict = {}
    raw_event: dict = {
        "requestContext": request_context,
        "pathParameters": path_params,
    }
    event.__getitem__ = lambda self, key: raw_event[key]
    event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
    event.get = lambda key, default=None: raw_event.get(key, default)
    app.current_event = event
    return app


class TestHawkAuthMiddlewareSuccess:
    def test_success_injects_hawk_uid(self):
        """Successful Hawk validation injects hawk_uid and calls next."""
        hawk_service = MagicMock()
        creds = HawkCredentials(
            user_id="user123",
            generation=5,
            expiry=9999999999,
            hawk_id="hawkid123",
        )
        hawk_service.validate.return_value = creds
        middleware = HawkAuthMiddleware(hawk_service=hawk_service)

        app = _make_app(auth_header='Hawk id="hawkid123"')
        mock_response = Response(status_code=200, body='{"ok": true}')
        mock_next = MagicMock(return_value=mock_response)

        result = middleware.handler(app, mock_next)

        # Verify hawk_service.validate was called with correct args
        hawk_service.validate.assert_called_once_with(
            'Hawk id="hawkid123"',
            "GET",
            "/1.5/123/storage/bookmarks",
            "storage.example.com",
            443,
            query_params=None,
        )

        # Verify hawk_uid was injected
        assert app.current_event["requestContext"]["hawk_uid"] == "user123"

        # Verify next middleware was called
        mock_next.assert_called_once_with(app)
        assert result.status_code == 200

    def test_lowercase_authorization_header(self):
        """Middleware finds lowercase 'authorization' header."""
        hawk_service = MagicMock()
        creds = HawkCredentials(
            user_id="user1",
            generation=0,
            expiry=9999999999,
            hawk_id="hid",
        )
        hawk_service.validate.return_value = creds
        middleware = HawkAuthMiddleware(hawk_service=hawk_service)

        app = MagicMock()
        headers = {"authorization": 'Hawk id="hid"'}
        event = MagicMock()
        event.headers = headers
        event.http_method = "GET"
        event.path = "/1.5/1/storage/tabs"
        event.query_string_parameters = None
        event.request_context.domain_name = "example.com"
        raw_event: dict = {"requestContext": {}, "pathParameters": None}
        event.__getitem__ = lambda self, key: raw_event[key]
        event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
        event.get = lambda key, default=None: raw_event.get(key, default)
        app.current_event = event

        mock_next = MagicMock(return_value=Response(status_code=200, body="ok"))
        result = middleware.handler(app, mock_next)

        hawk_service.validate.assert_called_once()
        mock_next.assert_called_once()
        assert result.status_code == 200


class TestHawkAuthMiddlewareFailure:
    def test_missing_auth_header_raises_error(self):
        """Missing Authorization header raises HawkAuthenticationError."""
        hawk_service = MagicMock()
        middleware = HawkAuthMiddleware(hawk_service=hawk_service)

        app = _make_app(auth_header=None)
        mock_next = MagicMock()

        with pytest.raises(HawkAuthenticationError):
            middleware.handler(app, mock_next)

        hawk_service.validate.assert_not_called()
        mock_next.assert_not_called()

    def test_hawk_validation_exception_raises_error(self):
        """Exception from hawk_service.validate raises HawkAuthenticationError."""
        hawk_service = MagicMock()
        hawk_service.validate.side_effect = Exception("MacMismatch")
        middleware = HawkAuthMiddleware(hawk_service=hawk_service)

        app = _make_app(auth_header='Hawk id="bad", mac="invalid"')
        mock_next = MagicMock()

        with pytest.raises(HawkAuthenticationError):
            middleware.handler(app, mock_next)

        mock_next.assert_not_called()


class TestHawkAuthMiddlewareQueryString:
    def test_query_string_included_in_path(self):
        """Query string parameters are appended to path for MAC validation."""
        hawk_service = MagicMock()
        creds = HawkCredentials(
            user_id="user1",
            generation=0,
            expiry=9999999999,
            hawk_id="hid",
        )
        hawk_service.validate.return_value = creds
        middleware = HawkAuthMiddleware(hawk_service=hawk_service)

        app = _make_app(
            auth_header='Hawk id="hid"',
            method="POST",
            path="/1.5/123/storage/bookmarks",
            query_params={"batch": "true", "commit": "true"},
        )
        mock_next = MagicMock(return_value=Response(status_code=200, body="ok"))

        middleware.handler(app, mock_next)

        # Verify path includes query string
        call_args = hawk_service.validate.call_args
        validated_path = call_args[0][2]
        assert "?" in validated_path
        assert "batch=true" in validated_path
        assert "commit=true" in validated_path


class TestHawkAuthMiddlewareHostFallback:
    def test_domain_name_attribute_error_falls_back_to_host_header(self):
        """When request_context.domain_name raises, falls back to host header."""
        hawk_service = MagicMock()
        creds = HawkCredentials(user_id="user1", generation=0, expiry=9999999999, hawk_id="hid")
        hawk_service.validate.return_value = creds
        middleware = HawkAuthMiddleware(hawk_service=hawk_service)

        app = MagicMock()
        # request_context without domain_name attribute triggers AttributeError
        rc = MagicMock(spec=[])
        raw_event: dict = {"requestContext": {}, "pathParameters": None}
        event = MagicMock()
        event.headers = {
            "Authorization": 'Hawk id="hid"',
            "host": "fallback.example.com",
        }
        event.http_method = "GET"
        event.path = "/test"
        event.query_string_parameters = None
        event.request_context = rc
        event.__getitem__ = lambda self, key: raw_event[key]
        event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
        event.get = lambda key, default=None: raw_event.get(key, default)
        app.current_event = event

        mock_next = MagicMock(return_value=Response(status_code=200, body="ok"))
        middleware.handler(app, mock_next)

        call_args = hawk_service.validate.call_args
        assert call_args[0][3] == "fallback.example.com"


class TestHawkAuthMiddlewareInit:
    def test_requires_hawk_service_or_token_manager(self):
        """Middleware requires at least one of hawk_service or token_manager."""
        with pytest.raises(ValueError, match="Either hawk_service or token_manager"):
            HawkAuthMiddleware()

    def test_session_mode_with_token_manager(self):
        """Middleware can be initialized with token_manager for session auth."""
        token_manager = MagicMock()
        middleware = HawkAuthMiddleware(token_manager=token_manager)
        assert middleware._token_manager is token_manager
        assert middleware._hawk_service is None

    def test_storage_mode_with_hawk_service(self):
        """Middleware can be initialized with hawk_service for storage auth."""
        hawk_service = MagicMock()
        middleware = HawkAuthMiddleware(hawk_service=hawk_service)
        assert middleware._hawk_service is hawk_service
        assert middleware._token_manager is None


class TestHawkAuthMiddlewareSessionMode:
    def test_session_hawk_success_injects_hawk_uid(self):
        """Session Hawk validation injects hawk_uid and calls next."""
        token_manager = MagicMock()
        token_manager.verify_session_hawk.return_value = "uid123"
        middleware = HawkAuthMiddleware(token_manager=token_manager)

        app = MagicMock()
        event = MagicMock()
        event.headers = {"authorization": 'Hawk id="tokenid"'}
        event.http_method = "GET"
        event.path = "/v1/session/status"
        event.query_string_parameters = None
        event.request_context.domain_name = "auth.example.com"
        raw_event: dict = {"requestContext": {}}
        event.__getitem__ = lambda self, key: raw_event[key]
        event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
        app.current_event = event

        mock_response = Response(status_code=200, body='{"state": "verified"}')
        mock_next = MagicMock(return_value=mock_response)

        result = middleware.handler(app, mock_next)

        assert raw_event["requestContext"]["hawk_uid"] == "uid123"
        assert raw_event["requestContext"]["hawk_token_id"] == "tokenid"
        mock_next.assert_called_once_with(app)
        assert result.status_code == 200

    def test_session_hawk_invalid_token_raises_error(self):
        """Invalid session token raises HawkAuthenticationError."""
        token_manager = MagicMock()
        token_manager.verify_session_hawk.return_value = None
        middleware = HawkAuthMiddleware(token_manager=token_manager)

        app = MagicMock()
        event = MagicMock()
        event.headers = {"authorization": 'Hawk id="bad"'}
        event.http_method = "GET"
        event.path = "/v1/session/status"
        event.query_string_parameters = None
        event.request_context.domain_name = "auth.example.com"
        raw_event: dict = {"requestContext": {}}
        event.__getitem__ = lambda self, key: raw_event[key]
        event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
        app.current_event = event

        mock_next = MagicMock()

        with pytest.raises(HawkAuthenticationError):
            middleware.handler(app, mock_next)

        mock_next.assert_not_called()
