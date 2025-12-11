"""Tests for ApiRouter"""

from unittest.mock import MagicMock, patch

from src.services.api_router import ApiRouter


def test_api_router_initialization():
    """Test that ApiRouter initializes with routes"""
    mock_route1 = MagicMock()
    mock_route2 = MagicMock()
    routes = [mock_route1, mock_route2]

    with patch("src.services.api_router.APIGatewayRestResolver") as mock_resolver_class:
        mock_resolver_instance = MagicMock()
        mock_resolver_class.return_value = mock_resolver_instance

        router = ApiRouter(routes=routes)

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
    expected_response = {"statusCode": 200, "body": "{}"}

    with patch("src.services.api_router.APIGatewayRestResolver") as mock_resolver_class:
        mock_resolver_instance = MagicMock()
        mock_resolver_instance.resolve.return_value = expected_response
        mock_resolver_class.return_value = mock_resolver_instance

        router = ApiRouter(routes=[])
        result = router.handler(event, context)

        # Verify resolver.resolve was called with event and context
        mock_resolver_instance.resolve.assert_called_once_with(event=event, context=context)
        assert result == expected_response


def test_api_router_handler_with_different_responses():
    """Test handler with various API responses"""

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
        with patch("src.services.api_router.APIGatewayRestResolver") as mock_resolver_class:
            mock_resolver_instance = MagicMock()
            mock_resolver_instance.resolve.return_value = expected_response
            mock_resolver_class.return_value = mock_resolver_instance

            router = ApiRouter(routes=[])
            result = router.handler({}, MagicMock())

            assert result == expected_response


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
        mock_resolver_instance.resolve.return_value = {"statusCode": 200}
        mock_resolver_class.return_value = mock_resolver_instance

        router = ApiRouter(routes=[])
        router.handler(event, context)

        # Verify context was passed through
        call_kwargs = mock_resolver_instance.resolve.call_args[1]
        assert call_kwargs["context"] == context
        assert call_kwargs["event"] == event
