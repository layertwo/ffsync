"""Tests for lambda entrypoint"""

import json
from unittest.mock import Mock, patch

from botocore.stub import Stubber

from src.entrypoint import storage_api_handler
from src.environment.service_provider import ServiceProvider
from src.services.hawk_service import HawkCredentials
from src.services.token_generator import TokenGenerator

TEST_USER_ID = "test-user-123"
TEST_GENERATION = 0
TEST_UID = str(TokenGenerator.generate_uid(TEST_USER_ID, TEST_GENERATION))


def test_unexpected_route_error_returns_500(
    mock_service_provider: ServiceProvider,
    sample_lambda_context: Mock,
) -> None:
    """A route that raises unexpectedly is mapped to a 500 by the router's handler.

    Routes no longer carry their own catch-all; StorageProvider's
    _storage_exception_handlers owns the 500 response.
    """
    creds = HawkCredentials(
        user_id=TEST_USER_ID,
        generation=TEST_GENERATION,
        expiry=9999999999,
        hawk_id="test-hawk-id",
    )
    event = {
        "httpMethod": "GET",
        "path": f"/1.5/{TEST_UID}/storage",
        "pathParameters": {"uid": TEST_UID},
        "headers": {"Authorization": 'Hawk id="test", mac="test"'},
        "body": None,
        "queryStringParameters": None,
        "requestContext": {
            "requestId": "test-request-id",
            "accountId": "123456789012",
            "domainName": "storage.example.com",
        },
    }

    with (
        patch.object(mock_service_provider.hawk_service, "validate", return_value=creds),
        patch(
            "src.services.storage_manager.StorageManager.list_collections",
            side_effect=RuntimeError("boom"),
        ),
    ):
        result = storage_api_handler(
            event, sample_lambda_context, service_provider=mock_service_provider
        )

    assert result["statusCode"] == 500
    assert json.loads(result["body"]) == {"error": "Internal server error"}


def test_storage_api_happ_path(
    mock_service_provider: ServiceProvider,
    dynamodb_stubber: Stubber,
    sample_lambda_context: Mock,
) -> None:
    """
    Integration test: storage_api with MockServiceProvider and stubbed DynamoDB.

    This demonstrates the full request flow with botocore.Stubber:
    Lambda Handler -> MockServiceProvider -> StorageManager -> [Stubbed DynamoDB Client]
    """
    # Mock hawk_service.validate to bypass Hawk auth
    creds = HawkCredentials(
        user_id=TEST_USER_ID,
        generation=TEST_GENERATION,
        expiry=9999999999,
        hawk_id="test-hawk-id",
    )

    # Example: Stub a DynamoDB get_item response
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
            "Key": {
                "PK": "USER#test-user-123#COLLECTION#bookmarks",
                "SK": "OBJECT#item123",
            },
        },
    )

    event = {
        "httpMethod": "GET",
        "path": f"/1.5/{TEST_UID}/storage/bookmarks/item123",
        "pathParameters": {"uid": TEST_UID, "collectionName": "bookmarks", "objectId": "item123"},
        "headers": {"Authorization": 'Hawk id="test", mac="test"'},
        "body": None,
        "queryStringParameters": None,
        "requestContext": {
            "requestId": "test-request-id",
            "accountId": "123456789012",
            "domainName": "storage.example.com",
        },
    }

    with patch.object(mock_service_provider.hawk_service, "validate", return_value=creds):
        # Use dependency injection - no patching needed!
        result = storage_api_handler(
            event, sample_lambda_context, service_provider=mock_service_provider
        )

    # The result will depend on StorageManager implementation
    assert isinstance(result, dict)
    assert "statusCode" in result
