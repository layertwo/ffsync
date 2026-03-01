"""Tests for StorageHawkMiddleware"""

import json
from unittest.mock import MagicMock

from aws_lambda_powertools.event_handler import Response

from src.services.api_router import StorageHawkMiddleware
from src.services.hawk_service import HawkCredentials


def _make_app(
    auth_header=None,
    method="GET",
    path="/1.5/123/storage/bookmarks",
    query_params=None,
    domain_name="storage.example.com",
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
    # Support dict-style access for event["requestContext"]["authorizer"] injection
    request_context = {}
    raw_event = {"requestContext": request_context}
    event.__getitem__ = lambda self, key: raw_event[key]
    event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
    app.current_event = event
    return app


class TestStorageHawkMiddlewareSuccess:
    def test_success_injects_authorizer_context(self):
        """Successful Hawk validation injects authorizer context and calls next."""
        hawk_service = MagicMock()
        creds = HawkCredentials(
            user_id="user123",
            generation=5,
            expiry=9999999999,
            hawk_id="hawkid123",
        )
        hawk_service.validate.return_value = creds
        middleware = StorageHawkMiddleware(hawk_service=hawk_service)

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
        )

        # Verify authorizer context was injected
        authorizer = app.current_event["requestContext"]["authorizer"]
        assert authorizer["user_id"] == "user123"
        assert authorizer["hawk_id"] == "hawkid123"
        assert authorizer["generation"] == "5"
        assert "authenticated_at" in authorizer

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
        middleware = StorageHawkMiddleware(hawk_service=hawk_service)

        app = MagicMock()
        headers = {"authorization": 'Hawk id="hid"'}
        event = MagicMock()
        event.headers = headers
        event.http_method = "GET"
        event.path = "/1.5/1/storage/tabs"
        event.query_string_parameters = None
        event.request_context.domain_name = "example.com"
        raw_event = {"requestContext": {}}
        event.__getitem__ = lambda self, key: raw_event[key]
        event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
        app.current_event = event

        mock_next = MagicMock(return_value=Response(status_code=200, body="ok"))
        result = middleware.handler(app, mock_next)

        hawk_service.validate.assert_called_once()
        mock_next.assert_called_once()
        assert result.status_code == 200


class TestStorageHawkMiddlewareFailure:
    def test_missing_auth_header_returns_401(self):
        """Missing Authorization header returns 401 without calling next."""
        hawk_service = MagicMock()
        middleware = StorageHawkMiddleware(hawk_service=hawk_service)

        app = _make_app(auth_header=None)
        mock_next = MagicMock()

        result = middleware.handler(app, mock_next)

        assert result.status_code == 401
        body = json.loads(result.body)
        assert body["error"] == "Unauthorized"
        hawk_service.validate.assert_not_called()
        mock_next.assert_not_called()

    def test_hawk_validation_exception_returns_401(self):
        """Exception from hawk_service.validate returns 401."""
        hawk_service = MagicMock()
        hawk_service.validate.side_effect = Exception("MacMismatch")
        middleware = StorageHawkMiddleware(hawk_service=hawk_service)

        app = _make_app(auth_header='Hawk id="bad", mac="invalid"')
        mock_next = MagicMock()

        result = middleware.handler(app, mock_next)

        assert result.status_code == 401
        body = json.loads(result.body)
        assert body["error"] == "Unauthorized"
        mock_next.assert_not_called()


class TestStorageHawkMiddlewareQueryString:
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
        middleware = StorageHawkMiddleware(hawk_service=hawk_service)

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


class TestStorageHawkMiddlewareHostFallback:
    def test_domain_name_attribute_error_falls_back_to_host_header(self):
        """When request_context.domain_name raises, falls back to host header."""
        hawk_service = MagicMock()
        creds = HawkCredentials(user_id="user1", generation=0, expiry=9999999999, hawk_id="hid")
        hawk_service.validate.return_value = creds
        middleware = StorageHawkMiddleware(hawk_service=hawk_service)

        app = MagicMock()
        # request_context without domain_name attribute triggers AttributeError
        rc = MagicMock(spec=[])
        raw_event = {"requestContext": {}}
        event = MagicMock()
        event.headers = {"Authorization": 'Hawk id="hid"', "host": "fallback.example.com"}
        event.http_method = "GET"
        event.path = "/test"
        event.query_string_parameters = None
        event.request_context = rc
        event.__getitem__ = lambda self, key: raw_event[key]
        event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
        app.current_event = event

        mock_next = MagicMock(return_value=Response(status_code=200, body="ok"))
        middleware.handler(app, mock_next)

        call_args = hawk_service.validate.call_args
        assert call_args[0][3] == "fallback.example.com"
