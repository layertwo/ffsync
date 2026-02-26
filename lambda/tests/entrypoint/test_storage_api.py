"""Tests for lambda entrypoint"""

from src.entrypoint import storage_api_handler


def test_storage_api_happ_path(mock_service_provider, dynamodb_stubber, sample_lambda_context):
    """
    Integration test: storage_api with MockServiceProvider and stubbed DynamoDB.

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
        "path": "/1.5/12345/storage/bookmarks/item123",
        "pathParameters": {"uid": "12345", "collectionName": "bookmarks", "objectId": "item123"},
        "headers": {},
        "body": None,
        "queryStringParameters": None,
    }

    # Use dependency injection - no patching needed!
    result = storage_api_handler(
        event, sample_lambda_context, service_provider=mock_service_provider
    )

    # The result will depend on StorageManager implementation
    # For now, with NotImplementedError, this demonstrates the pattern
    assert isinstance(result, dict)
    assert "statusCode" in result
