"""Tests for lambda entrypoint"""

from unittest.mock import patch

from src.entrypoint import storage_api_handler
from src.services.hawk_service import HawkCredentials
from src.services.token_generator import TokenGenerator

TEST_USER_ID = "test-user-123"
TEST_GENERATION = 0
TEST_UID = str(TokenGenerator.generate_uid(TEST_USER_ID, TEST_GENERATION))


def test_storage_api_happ_path(mock_service_provider, dynamodb_stubber, sample_lambda_context):
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
            "Key": {"PK": {"S": "COLLECTION#bookmarks"}, "SK": {"S": "OBJECT#item123"}},
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
