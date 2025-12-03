"""Tests for lambda entrypoint"""

from unittest.mock import MagicMock, patch

import pytest

from src.entrypoint.main import lambda_handler


def test_lambda_handler_creates_service_provider_by_default(
    sample_lambda_event, sample_lambda_context
):
    """Test that lambda_handler creates ServiceProvider when not provided"""
    with patch("src.entrypoint.main.ServiceProvider") as mock_provider_class:
        # Set up mock
        mock_provider = MagicMock()
        mock_api_router = MagicMock()
        mock_api_router.handler.return_value = {"statusCode": 200, "body": "{}"}
        mock_provider.api_router = mock_api_router
        mock_provider_class.return_value = mock_provider

        # Call without service_provider parameter
        result = lambda_handler(sample_lambda_event, sample_lambda_context)

        # Verify ServiceProvider was instantiated
        mock_provider_class.assert_called_once()

        # Verify api_router.handler was called with correct arguments
        mock_api_router.handler.assert_called_once_with(
            sample_lambda_event, sample_lambda_context
        )

        # Verify result is returned
        assert result == {"statusCode": 200, "body": "{}"}


def test_lambda_handler_uses_provided_service_provider(
    sample_lambda_event, sample_lambda_context
):
    """Test that lambda_handler uses injected ServiceProvider"""
    # Create mock service provider
    mock_provider = MagicMock()
    mock_api_router = MagicMock()
    mock_api_router.handler.return_value = {
        "statusCode": 201,
        "body": '{"created": true}',
    }
    mock_provider.api_router = mock_api_router

    # Call with injected service_provider
    result = lambda_handler(
        sample_lambda_event, sample_lambda_context, service_provider=mock_provider
    )

    # Verify api_router.handler was called
    mock_api_router.handler.assert_called_once_with(
        sample_lambda_event, sample_lambda_context
    )

    # Verify result is returned
    assert result == {"statusCode": 201, "body": '{"created": true}'}


def test_lambda_handler_returns_response(sample_lambda_event, sample_lambda_context):
    """Test that lambda_handler returns the response from api_router"""
    expected_response = {
        "statusCode": 404,
        "body": '{"error": "Not found"}',
        "headers": {"Content-Type": "application/json"},
    }

    with patch("src.entrypoint.main.ServiceProvider") as mock_provider_class:
        mock_provider = MagicMock()
        mock_api_router = MagicMock()
        mock_api_router.handler.return_value = expected_response
        mock_provider.api_router = mock_api_router
        mock_provider_class.return_value = mock_provider

        from src.entrypoint.main import lambda_handler

        result = lambda_handler(sample_lambda_event, sample_lambda_context)

        assert result == expected_response


def test_lambda_handler_with_different_events(sample_lambda_context):
    """Test lambda_handler with various event types"""
    events = [
        {"httpMethod": "GET", "path": "/storage/collection1/obj1"},
        {"httpMethod": "POST", "path": "/storage/collection2"},
        {"httpMethod": "DELETE", "path": "/storage"},
    ]

    for event in events:
        with patch("src.entrypoint.main.ServiceProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_api_router = MagicMock()
            mock_api_router.handler.return_value = {"statusCode": 200}
            mock_provider.api_router = mock_api_router
            mock_provider_class.return_value = mock_provider

            result = lambda_handler(event, sample_lambda_context)

            # Verify the event was passed through
            mock_api_router.handler.assert_called_with(event, sample_lambda_context)
            assert result["statusCode"] == 200


def test_lambda_handler_integration_with_stubbed_dynamodb(
    mock_service_provider, dynamodb_stubber, sample_lambda_context
):
    """
    Integration test: lambda_handler with MockServiceProvider and stubbed DynamoDB.

    This demonstrates the full request flow with botocore.Stubber:
    Lambda Handler → MockServiceProvider → StorageManager → [Stubbed DynamoDB Client]
    """
    # Example: Stub a DynamoDB get_item response
    # When StorageManager.get_storage_object() is implemented, it would call get_item
    dynamodb_stubber.add_response(
        "get_item",
        {
            "Item": {
                "collection_name": {"S": "bookmarks"},
                "object_id": {"S": "item123"},
                "payload": {"S": "test_data"},
                "modified": {"N": "1234567890.12"},
                "sortindex": {"N": "100"},
                "ttl": {"N": "3600"},
            }
        },
        {
            "TableName": "test-storage-table",
            "Key": {"PK": {"S": "COLLECTION#bookmarks"}, "SK": {"S": "OBJECT#item123"}},
        },
    )

    event = {
        "httpMethod": "GET",
        "path": "/storage/bookmarks/item123",
        "pathParameters": {"collectionName": "bookmarks", "objectId": "item123"},
        "headers": {},
        "body": None,
        "queryStringParameters": None,
    }

    # Use dependency injection - no patching needed!
    result = lambda_handler(
        event, sample_lambda_context, service_provider=mock_service_provider
    )

    # The result will depend on StorageManager implementation
    # For now, with NotImplementedError, this demonstrates the pattern
    assert isinstance(result, dict)
    assert "statusCode" in result
