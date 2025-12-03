"""Tests for ApiRouter"""

from unittest.mock import MagicMock, patch

import pytest


def test_api_router_initialization():
    """Test that ApiRouter initializes with routes"""
    from src.services.api_router import ApiRouter

    mock_route1 = MagicMock()
    mock_route2 = MagicMock()
    routes = [mock_route1, mock_route2]

    with patch("src.services.api_router.API") as mock_api_class:
        mock_api_instance = MagicMock()
        mock_api_class.return_value = mock_api_instance

        router = ApiRouter(routes=routes)

        # Verify API was created with correct parameters
        mock_api_class.assert_called_once_with(name="StorageAPI", version="1.0")

        # Verify routes were registered
        mock_route1.bind.assert_called_once_with(mock_api_instance)
        mock_route2.bind.assert_called_once_with(mock_api_instance)

        assert router.api == mock_api_instance
        assert router._routes == routes


def test_api_router_register_routes():
    """Test that _register_routes calls bind on all routes"""
    from src.services.api_router import ApiRouter

    mock_routes = [MagicMock() for _ in range(5)]

    with patch("src.services.api_router.API") as mock_api_class:
        mock_api_instance = MagicMock()
        mock_api_class.return_value = mock_api_instance

        router = ApiRouter(routes=mock_routes)

        # Verify each route's bind method was called with the API instance
        for mock_route in mock_routes:
            mock_route.bind.assert_called_once_with(mock_api_instance)


def test_api_router_handler_calls_api():
    """Test that handler method calls the API instance"""
    from src.services.api_router import ApiRouter

    event = {"httpMethod": "GET", "path": "/test"}
    context = MagicMock()
    expected_response = {"statusCode": 200, "body": "{}"}

    with patch("src.services.api_router.API") as mock_api_class:
        mock_api_instance = MagicMock()
        mock_api_instance.return_value = expected_response
        mock_api_class.return_value = mock_api_instance

        router = ApiRouter(routes=[])
        result = router.handler(event, context)

        # Verify API instance was called with event and context
        mock_api_instance.assert_called_once_with(event=event, context=context)
        assert result == expected_response


def test_api_router_handler_logs_event():
    """Test that handler logs the incoming event"""
    from src.services.api_router import ApiRouter

    event = {"httpMethod": "POST", "path": "/storage/collection"}
    context = MagicMock()

    with patch("src.services.api_router.API") as mock_api_class:
        with patch("src.services.api_router.logger") as mock_logger:
            mock_api_instance = MagicMock()
            mock_api_instance.return_value = {"statusCode": 201}
            mock_api_class.return_value = mock_api_instance

            router = ApiRouter(routes=[])
            router.handler(event, context)

            # Verify logger.info was called with the event
            mock_logger.info.assert_called_once()
            call_args = str(mock_logger.info.call_args[0][0])
            assert "Received event:" in call_args


def test_api_router_handler_with_different_responses():
    """Test handler with various API responses"""
    from src.services.api_router import ApiRouter

    test_cases = [
        {"statusCode": 200, "body": '{"result": "success"}'},
        {"statusCode": 404, "body": '{"error": "Not found"}'},
        {"statusCode": 500, "body": '{"error": "Internal error"}'},
        {
            "statusCode": 201,
            "body": '{"created": true}',
            "headers": {"X-Custom": "value"},
        },
    ]

    for expected_response in test_cases:
        with patch("src.services.api_router.API") as mock_api_class:
            mock_api_instance = MagicMock()
            mock_api_instance.return_value = expected_response
            mock_api_class.return_value = mock_api_instance

            router = ApiRouter(routes=[])
            result = router.handler({}, MagicMock())

            assert result == expected_response


def test_api_router_empty_routes():
    """Test ApiRouter with no routes"""
    from src.services.api_router import ApiRouter

    with patch("src.services.api_router.API") as mock_api_class:
        mock_api_instance = MagicMock()
        mock_api_class.return_value = mock_api_instance

        router = ApiRouter(routes=[])

        # Verify API was created
        mock_api_class.assert_called_once()
        assert router._routes == []


def test_api_router_handler_passes_context():
    """Test that handler passes context correctly to API"""
    from src.services.api_router import ApiRouter

    event = {"test": "event"}
    context = MagicMock()
    context.function_name = "test-function"
    context.aws_request_id = "test-request-id"

    with patch("src.services.api_router.API") as mock_api_class:
        mock_api_instance = MagicMock()
        mock_api_instance.return_value = {"statusCode": 200}
        mock_api_class.return_value = mock_api_instance

        router = ApiRouter(routes=[])
        router.handler(event, context)

        # Verify context was passed through
        call_kwargs = mock_api_instance.call_args[1]
        assert call_kwargs["context"] == context
        assert call_kwargs["event"] == event
