"""Tests for ApiRouter"""

from unittest.mock import MagicMock, patch

from aws_lambda_powertools.event_handler import Response

from src.services.api_router import (
    ApiRouter,
    HawkAuthenticationError,
    HawkAuthMiddleware,
    RequestLoggingMiddleware,
    UidMismatchError,
    WeaveTimestampMiddleware,
)
from src.services.token_generator import TokenGenerator


def test_api_router_initialization():
    """Test that ApiRouter initializes with routes"""
    mock_route1 = MagicMock()
    mock_route2 = MagicMock()
    routes = [mock_route1, mock_route2]

    with patch("src.services.api_router.APIGatewayRestResolver") as mock_resolver_class:
        mock_resolver_instance = MagicMock()
        mock_resolver_class.return_value = mock_resolver_instance

        router = ApiRouter(routes=routes, middlewares=[])  # type: ignore[arg-type]

        # Verify resolver was created
        mock_resolver_class.assert_called_once()

        # Verify routes were registered
        mock_route1.bind.assert_called_once_with(mock_resolver_instance)
        mock_route2.bind.assert_called_once_with(mock_resolver_instance)

        assert router.app == mock_resolver_instance
        assert router._routes == routes


def test_api_router_handler_calls_resolver():
    """Test that handler method calls the resolver's resolve method"""
    event = {"httpMethod": "GET", "path": "/test"}
    context = MagicMock()

    with patch("src.services.api_router.APIGatewayRestResolver") as mock_resolver_class:
        mock_resolver_instance = MagicMock()
        mock_resolver_class.return_value = mock_resolver_instance

        router = ApiRouter(routes=[], middlewares=[])
        router.handler(event, context)

        # Verify resolver.resolve was called with event and context
        mock_resolver_instance.resolve.assert_called_once_with(event=event, context=context)


def test_api_router_handler_with_different_responses():
    """Test middleware adds X-Weave-Timestamp to various responses"""
    with patch("src.middlewares.weave_timestamp.get_weave_timestamp") as mock_timestamp:
        mock_timestamp.return_value = "1702345678.12"

        middleware = WeaveTimestampMiddleware()
        mock_app = MagicMock()

        test_cases = [
            Response(status_code=200, body='{"result": "success"}'),
            Response(status_code=404, body='{"error": "Not found"}'),
            Response(status_code=500, body='{"error": "Internal error"}'),
            Response(
                status_code=201,
                body='{"created": true}',
                headers={"X-Custom": "value"},
            ),
        ]

        for response in test_cases:
            # Mock next_middleware to return the response
            mock_next = MagicMock(return_value=response)

            result = middleware.handler(mock_app, mock_next)

            # Verify X-Weave-Timestamp header was added
            assert "X-Weave-Timestamp" in result.headers
            assert result.headers["X-Weave-Timestamp"] == "1702345678.12"

            # Verify existing headers are preserved
            if response.headers:
                for key, value in response.headers.items():
                    if key != "X-Weave-Timestamp":
                        assert result.headers[key] == value


def test_api_router_empty_routes():
    """Test ApiRouter with no routes"""
    with patch("src.services.api_router.APIGatewayRestResolver") as mock_resolver_class:
        mock_resolver_instance = MagicMock()
        mock_resolver_class.return_value = mock_resolver_instance

        router = ApiRouter(routes=[], middlewares=[])

        # Verify resolver was created
        mock_resolver_class.assert_called_once()
        assert router._routes == []


def test_api_router_handler_passes_context():
    """Test that handler passes context correctly to resolver"""
    event = {"test": "event"}
    context = MagicMock()
    context.function_name = "test-function"
    context.aws_request_id = "test-request-id"

    with patch("src.services.api_router.APIGatewayRestResolver") as mock_resolver_class:
        mock_resolver_instance = MagicMock()
        mock_resolver_class.return_value = mock_resolver_instance

        router = ApiRouter(routes=[], middlewares=[])
        router.handler(event, context)

        # Verify context was passed through
        call_kwargs = mock_resolver_instance.resolve.call_args[1]
        assert call_kwargs["context"] == context
        assert call_kwargs["event"] == event


def test_api_router_adds_x_weave_timestamp_to_all_responses():
    """Test that X-Weave-Timestamp header is added to all responses (Requirements 9.1-9.4)"""
    with patch("src.middlewares.weave_timestamp.get_weave_timestamp") as mock_timestamp:
        mock_timestamp.return_value = "1702345678.12"

        middleware = WeaveTimestampMiddleware()
        mock_app = MagicMock()
        mock_response = Response(status_code=200, body='{"test": "data"}')
        mock_next = MagicMock(return_value=mock_response)

        result = middleware.handler(mock_app, mock_next)

        # Verify X-Weave-Timestamp header is present
        assert "X-Weave-Timestamp" in result.headers
        assert result.headers["X-Weave-Timestamp"] == "1702345678.12"


def test_weave_timestamp_middleware_preserves_existing_headers():
    """Test that middleware preserves existing response headers"""
    with patch("src.middlewares.weave_timestamp.get_weave_timestamp") as mock_timestamp:
        mock_timestamp.return_value = "1702345678.12"

        middleware = WeaveTimestampMiddleware()
        mock_app = MagicMock()
        mock_response = Response(
            status_code=200,
            body='{"test": "data"}',
            headers={"X-Custom": "value", "Content-Type": "application/json"},
        )
        mock_next = MagicMock(return_value=mock_response)

        result = middleware.handler(mock_app, mock_next)

        # Verify all headers are present
        assert result.headers["X-Weave-Timestamp"] == "1702345678.12"
        assert result.headers["X-Custom"] == "value"
        assert result.headers["Content-Type"] == "application/json"


def test_api_router_registers_middleware():
    """Test that ApiRouter registers both RequestLoggingMiddleware and WeaveTimestampMiddleware"""
    with patch("src.services.api_router.APIGatewayRestResolver") as mock_resolver_class:
        mock_resolver_instance = MagicMock()
        mock_resolver_class.return_value = mock_resolver_instance

        request_logging = RequestLoggingMiddleware()
        weave_timestamp = WeaveTimestampMiddleware()
        middlewares = [request_logging, weave_timestamp]

        ApiRouter(routes=[], middlewares=middlewares)

        # Verify middleware was registered
        mock_resolver_instance.use.assert_called_once()
        registered_middlewares = mock_resolver_instance.use.call_args[1]["middlewares"]
        assert len(registered_middlewares) == 2
        assert registered_middlewares[0] is request_logging
        assert registered_middlewares[1] is weave_timestamp


def test_weave_timestamp_middleware_calls_next():
    """Test that middleware calls the next handler in the chain"""
    with patch("src.middlewares.weave_timestamp.get_weave_timestamp") as mock_timestamp:
        mock_timestamp.return_value = "1702345678.12"

        middleware = WeaveTimestampMiddleware()
        mock_app = MagicMock()
        mock_response = Response(status_code=200, body='{"test": "data"}')
        mock_next = MagicMock(return_value=mock_response)

        middleware.handler(mock_app, mock_next)

        # Verify next middleware was called
        mock_next.assert_called_once_with(mock_app)


def test_request_logging_middleware_logs_request_and_response():
    """Test that RequestLoggingMiddleware logs request and response information (Requirements 14.1-14.4)"""
    with patch("src.middlewares.request_logging.logger") as mock_logger:
        middleware = RequestLoggingMiddleware()
        mock_app = MagicMock()
        mock_app.current_event = {
            "httpMethod": "GET",
            "path": "/1.5/12345/storage/bookmarks",
            "requestContext": {"hawk_uid": "user123"},
        }
        mock_response = Response(status_code=200, body='{"test": "data"}')
        mock_next = MagicMock(return_value=mock_response)

        result = middleware.handler(mock_app, mock_next)

        # Verify request received was logged
        assert mock_logger.info.call_count == 2
        first_call = mock_logger.info.call_args_list[0]
        assert first_call[0][0] == "Request received"
        assert first_call[1]["extra"]["method"] == "GET"
        assert first_call[1]["extra"]["path"] == "/1.5/12345/storage/bookmarks"
        assert first_call[1]["extra"]["user_id"] == "user123"

        # Verify request completed was logged
        second_call = mock_logger.info.call_args_list[1]
        assert second_call[0][0] == "Request completed"
        assert second_call[1]["extra"]["method"] == "GET"
        assert second_call[1]["extra"]["path"] == "/1.5/12345/storage/bookmarks"
        assert second_call[1]["extra"]["user_id"] == "user123"
        assert second_call[1]["extra"]["status_code"] == 200
        assert "duration_ms" in second_call[1]["extra"]

        # Verify response is returned
        assert result == mock_response


def test_request_logging_middleware_logs_anonymous_user():
    """Test that RequestLoggingMiddleware logs 'anonymous' when hawk_uid is not present"""
    with patch("src.middlewares.request_logging.logger") as mock_logger:
        middleware = RequestLoggingMiddleware()
        mock_app = MagicMock()
        mock_app.current_event = {
            "httpMethod": "GET",
            "path": "/1.5/12345/info/configuration",
            "requestContext": {},
        }
        mock_response = Response(status_code=200, body='{"test": "data"}')
        mock_next = MagicMock(return_value=mock_response)

        middleware.handler(mock_app, mock_next)

        # Verify anonymous user was logged
        first_call = mock_logger.info.call_args_list[0]
        assert first_call[1]["extra"]["user_id"] == "anonymous"


def test_request_logging_middleware_logs_errors():
    """Test that RequestLoggingMiddleware logs errors with stack trace (Requirements 14.2)"""
    with patch("src.middlewares.request_logging.logger") as mock_logger:
        middleware = RequestLoggingMiddleware()
        mock_app = MagicMock()
        mock_app.current_event = {
            "httpMethod": "POST",
            "path": "/1.5/12345/storage/bookmarks",
            "requestContext": {"hawk_uid": "user123"},
        }
        test_exception = ValueError("Test error")
        mock_next = MagicMock(side_effect=test_exception)

        # Verify exception is re-raised
        try:
            middleware.handler(mock_app, mock_next)
            assert False, "Expected exception to be raised"
        except ValueError:
            pass

        # Verify request received was logged
        assert mock_logger.info.call_count == 1

        # Verify error was logged
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args
        assert error_call[0][0] == "Request failed"
        assert error_call[1]["extra"]["method"] == "POST"
        assert error_call[1]["extra"]["path"] == "/1.5/12345/storage/bookmarks"
        assert error_call[1]["extra"]["user_id"] == "user123"
        assert error_call[1]["extra"]["error_type"] == "ValueError"
        assert error_call[1]["extra"]["error_message"] == "Test error"
        assert "duration_ms" in error_call[1]["extra"]
        assert error_call[1]["exc_info"] is True  # Stack trace included


def test_request_logging_middleware_never_logs_payloads():
    """Test that RequestLoggingMiddleware never logs BSO payloads (Requirements 14.4)"""
    with patch("src.middlewares.request_logging.logger") as mock_logger:
        middleware = RequestLoggingMiddleware()
        mock_app = MagicMock()
        # Event with body containing sensitive data
        mock_app.current_event = {
            "httpMethod": "PUT",
            "path": "/1.5/12345/storage/bookmarks/abc123",
            "body": '{"payload": "sensitive encrypted data", "sortindex": 100}',
            "requestContext": {"hawk_uid": "user123"},
        }
        mock_response = Response(status_code=200, body='{"modified": 1702345678.12}')
        mock_next = MagicMock(return_value=mock_response)

        middleware.handler(mock_app, mock_next)

        # Verify no log call contains the sensitive payload
        for call in mock_logger.info.call_args_list:
            log_message = str(call)
            assert "sensitive encrypted data" not in log_message
            assert "body" not in str(call[1].get("extra", {}))


class TestHawkAuthMiddlewareUidValidation:
    """Tests for HawkAuthMiddleware UID validation (replaces UidValidationMiddleware)"""

    def test_matching_uid_passes_through(self):
        """Test that a matching uid allows the request to proceed"""
        hawk_service = MagicMock()
        user_id = "test-user-123"
        generation = 0
        expected_uid = str(TokenGenerator.generate_uid(user_id, generation))

        from src.services.hawk_service import HawkCredentials

        creds = HawkCredentials(
            user_id=user_id,
            generation=generation,
            expiry=9999999999,
            hawk_id="hawkid123",
        )
        hawk_service.validate.return_value = creds
        middleware = HawkAuthMiddleware(hawk_service=hawk_service)

        mock_app = MagicMock()
        event = MagicMock()
        event.headers = {"Authorization": 'Hawk id="hawkid123"'}
        event.http_method = "GET"
        event.path = f"/1.5/{expected_uid}/storage/bookmarks"
        event.query_string_parameters = None
        event.request_context.domain_name = "storage.example.com"
        raw_event: dict = {
            "requestContext": {},
            "pathParameters": {"uid": expected_uid},
        }
        event.__getitem__ = lambda self, key: raw_event[key]
        event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
        event.get = lambda key, default=None: raw_event.get(key, default)
        mock_app.current_event = event

        mock_response = Response(status_code=200, body='{"ok": true}')
        mock_next = MagicMock(return_value=mock_response)

        result = middleware.handler(mock_app, mock_next)

        mock_next.assert_called_once_with(mock_app)
        assert result.status_code == 200

    def test_mismatched_uid_raises_uid_mismatch_error(self):
        """Test that a mismatched uid raises UidMismatchError"""
        hawk_service = MagicMock()
        user_id = "test-user-123"
        generation = 0

        from src.services.hawk_service import HawkCredentials

        creds = HawkCredentials(
            user_id=user_id,
            generation=generation,
            expiry=9999999999,
            hawk_id="hawkid123",
        )
        hawk_service.validate.return_value = creds
        middleware = HawkAuthMiddleware(hawk_service=hawk_service)

        mock_app = MagicMock()
        event = MagicMock()
        event.headers = {"Authorization": 'Hawk id="hawkid123"'}
        event.http_method = "GET"
        event.path = "/1.5/wrong-uid/storage/bookmarks"
        event.query_string_parameters = None
        event.request_context.domain_name = "storage.example.com"
        raw_event: dict = {
            "requestContext": {},
            "pathParameters": {"uid": "wrong-uid"},
        }
        event.__getitem__ = lambda self, key: raw_event[key]
        event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
        event.get = lambda key, default=None: raw_event.get(key, default)
        mock_app.current_event = event

        mock_next = MagicMock()

        import pytest

        with pytest.raises(UidMismatchError):
            middleware.handler(mock_app, mock_next)

        mock_next.assert_not_called()

    def test_missing_uid_skips_validation(self):
        """Test that missing uid path parameter skips UID validation"""
        hawk_service = MagicMock()
        user_id = "test-user-123"

        from src.services.hawk_service import HawkCredentials

        creds = HawkCredentials(
            user_id=user_id,
            generation=0,
            expiry=9999999999,
            hawk_id="hawkid123",
        )
        hawk_service.validate.return_value = creds
        middleware = HawkAuthMiddleware(hawk_service=hawk_service)

        mock_app = MagicMock()
        event = MagicMock()
        event.headers = {"Authorization": 'Hawk id="hawkid123"'}
        event.http_method = "GET"
        event.path = "/test"
        event.query_string_parameters = None
        event.request_context.domain_name = "storage.example.com"
        raw_event: dict = {
            "requestContext": {},
            "pathParameters": {},
        }
        event.__getitem__ = lambda self, key: raw_event[key]
        event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
        event.get = lambda key, default=None: raw_event.get(key, default)
        mock_app.current_event = event

        mock_response = Response(status_code=200, body='{"ok": true}')
        mock_next = MagicMock(return_value=mock_response)

        result = middleware.handler(mock_app, mock_next)

        mock_next.assert_called_once_with(mock_app)
        assert result.status_code == 200

    def test_null_path_parameters_skips_validation(self):
        """Test that null pathParameters skips UID validation"""
        hawk_service = MagicMock()
        user_id = "test-user-123"

        from src.services.hawk_service import HawkCredentials

        creds = HawkCredentials(
            user_id=user_id,
            generation=0,
            expiry=9999999999,
            hawk_id="hawkid123",
        )
        hawk_service.validate.return_value = creds
        middleware = HawkAuthMiddleware(hawk_service=hawk_service)

        mock_app = MagicMock()
        event = MagicMock()
        event.headers = {"Authorization": 'Hawk id="hawkid123"'}
        event.http_method = "GET"
        event.path = "/test"
        event.query_string_parameters = None
        event.request_context.domain_name = "storage.example.com"
        raw_event: dict = {
            "requestContext": {},
            "pathParameters": None,
        }
        event.__getitem__ = lambda self, key: raw_event[key]
        event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
        event.get = lambda key, default=None: raw_event.get(key, default)
        mock_app.current_event = event

        mock_response = Response(status_code=200, body='{"ok": true}')
        mock_next = MagicMock(return_value=mock_response)

        result = middleware.handler(mock_app, mock_next)

        mock_next.assert_called_once_with(mock_app)
        assert result.status_code == 200

    def test_different_generation_produces_different_uid(self):
        """Test that different generation values produce different expected uids"""
        hawk_service = MagicMock()
        user_id = "test-user-123"
        gen0_uid = str(TokenGenerator.generate_uid(user_id, 0))
        gen1_uid = str(TokenGenerator.generate_uid(user_id, 1))

        from src.services.hawk_service import HawkCredentials

        # Request with gen0 uid but gen1 in credentials should fail
        creds = HawkCredentials(
            user_id=user_id,
            generation=1,
            expiry=9999999999,
            hawk_id="hawkid123",
        )
        hawk_service.validate.return_value = creds
        middleware = HawkAuthMiddleware(hawk_service=hawk_service)

        mock_app = MagicMock()
        event = MagicMock()
        event.headers = {"Authorization": 'Hawk id="hawkid123"'}
        event.http_method = "GET"
        event.path = f"/1.5/{gen0_uid}/storage/bookmarks"
        event.query_string_parameters = None
        event.request_context.domain_name = "storage.example.com"
        raw_event: dict = {
            "requestContext": {},
            "pathParameters": {"uid": gen0_uid},
        }
        event.__getitem__ = lambda self, key: raw_event[key]
        event.__setitem__ = lambda self, key, val: raw_event.__setitem__(key, val)
        event.get = lambda key, default=None: raw_event.get(key, default)
        mock_app.current_event = event

        mock_next = MagicMock()

        import pytest

        with pytest.raises(UidMismatchError):
            middleware.handler(mock_app, mock_next)

        mock_next.assert_not_called()

        # But gen1 uid with gen1 in credentials should pass
        raw_event["pathParameters"]["uid"] = gen1_uid
        mock_response = Response(status_code=200, body='{"ok": true}')
        mock_next_pass = MagicMock(return_value=mock_response)

        result = middleware.handler(mock_app, mock_next_pass)

        mock_next_pass.assert_called_once_with(mock_app)
        assert result.status_code == 200


def test_api_router_registers_exception_handlers():
    """Test that ApiRouter registers exception handlers"""
    with patch("src.services.api_router.APIGatewayRestResolver") as mock_resolver_class:
        mock_resolver_instance = MagicMock()
        mock_resolver_class.return_value = mock_resolver_instance

        def handle_hawk_auth(ex):
            return Response(status_code=401, body='{"error": "Unauthorized"}')

        def handle_uid_mismatch(ex):
            return Response(status_code=403, body='{"error": "uid mismatch"}')

        exception_handlers = {
            HawkAuthenticationError: handle_hawk_auth,
            UidMismatchError: handle_uid_mismatch,
        }

        ApiRouter(
            routes=[],
            middlewares=[],
            exception_handlers=exception_handlers,
        )

        # Verify exception_handler was called for each handler
        assert mock_resolver_instance.exception_handler.call_count == 2
