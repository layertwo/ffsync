"""Tests for ApiRouter"""

from unittest.mock import MagicMock, patch

from aws_lambda_powertools.event_handler import Response

from src.services.api_router import ApiRouter, WeaveTimestampMiddleware


def test_api_router_initialization():
    """Test that ApiRouter initializes with routes"""
    mock_route1 = MagicMock()
    mock_route2 = MagicMock()
    routes = [mock_route1, mock_route2]

    with patch("src.services.api_router.APIGatewayRestResolver") as mock_resolver_class:
        mock_resolver_instance = MagicMock()
        mock_resolver_class.return_value = mock_resolver_instance

        router = ApiRouter(routes=routes)  # type: ignore[arg-type]

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

        router = ApiRouter(routes=[])
        router.handler(event, context)

        # Verify resolver.resolve was called with event and context
        mock_resolver_instance.resolve.assert_called_once_with(event=event, context=context)


def test_api_router_handler_with_different_responses():
    """Test middleware adds X-Weave-Timestamp to various responses"""
    with patch("src.services.api_router.get_weave_timestamp") as mock_timestamp:
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

        router = ApiRouter(routes=[])

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

        router = ApiRouter(routes=[])
        router.handler(event, context)

        # Verify context was passed through
        call_kwargs = mock_resolver_instance.resolve.call_args[1]
        assert call_kwargs["context"] == context
        assert call_kwargs["event"] == event


def test_api_router_adds_x_weave_timestamp_to_all_responses():
    """Test that X-Weave-Timestamp header is added to all responses (Requirements 9.1-9.4)"""
    with patch("src.services.api_router.get_weave_timestamp") as mock_timestamp:
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
    with patch("src.services.api_router.get_weave_timestamp") as mock_timestamp:
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
    """Test that ApiRouter registers the WeaveTimestampMiddleware"""
    with patch("src.services.api_router.APIGatewayRestResolver") as mock_resolver_class:
        mock_resolver_instance = MagicMock()
        mock_resolver_class.return_value = mock_resolver_instance

        ApiRouter(routes=[])

        # Verify middleware was registered
        mock_resolver_instance.use.assert_called_once()
        middlewares = mock_resolver_instance.use.call_args[1]["middlewares"]
        assert len(middlewares) == 1
        assert isinstance(middlewares[0], WeaveTimestampMiddleware)


def test_weave_timestamp_middleware_calls_next():
    """Test that middleware calls the next handler in the chain"""
    with patch("src.services.api_router.get_weave_timestamp") as mock_timestamp:
        mock_timestamp.return_value = "1702345678.12"

        middleware = WeaveTimestampMiddleware()
        mock_app = MagicMock()
        mock_response = Response(status_code=200, body='{"test": "data"}')
        mock_next = MagicMock(return_value=mock_response)

        middleware.handler(mock_app, mock_next)

        # Verify next middleware was called
        mock_next.assert_called_once_with(mock_app)
