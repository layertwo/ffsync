"""Unit tests for StorageManager with DynamoDB stubber"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.services.storage_manager import StorageManager
from src.shared.exceptions import (
    CollectionNotFoundException,
    StorageObjectNotFoundException,
)
from src.shared.models import BasicStorageObject


class TestStorageManager:
    """Test StorageManager DynamoDB operations"""

    @pytest.fixture
    def storage_manager(self, dynamodb_table):
        """Create StorageManager instance with stubbed table"""
        return StorageManager(table=dynamodb_table)

    def test_get_collection_success(self, storage_manager, dynamodb_stubber, storage_table_name):
        """Test successful collection retrieval"""
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567890.12"},
                    "count": {"N": "5"},
                    "usage": {"N": "1024"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        collection = storage_manager.get_collection("test-user-123", "bookmarks")

        assert collection.name == "bookmarks"
        assert collection.modified == datetime.fromtimestamp(1234567890.12, tz=timezone.utc)
        assert collection.count == 5
        assert collection.usage == 1024

    def test_get_collection_not_found(self, storage_manager, dynamodb_stubber, storage_table_name):
        """Test collection not found"""
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#nonexistent",
                    "SK": "METADATA",
                },
            },
        )

        with pytest.raises(CollectionNotFoundException):
            storage_manager.get_collection("test-user-123", "nonexistent")

    def test_get_storage_object_success(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test successful storage object retrieval"""
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "test_payload"},
                    "modified": {"N": "1234567890.12"},
                    "sortindex": {"N": "100"},
                    "ttl": {"N": "3600"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        obj = storage_manager.get_storage_object("test-user-123", "bookmarks", "obj123")

        assert obj.id == "obj123"
        assert obj.payload == "test_payload"
        assert obj.modified == datetime.fromtimestamp(1234567890.12, tz=timezone.utc)
        assert obj.sortindex == 100
        assert obj.ttl == 3600

    def test_get_storage_object_not_found(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test storage object not found"""
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#nonexistent",
                },
            },
        )

        with pytest.raises(StorageObjectNotFoundException):
            storage_manager.get_storage_object("test-user-123", "bookmarks", "nonexistent")

    def test_get_storage_object_without_optional_fields(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test retrieval of storage object without sortindex and ttl"""
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "test_payload"},
                    "modified": {"N": "1234567890.12"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        obj = storage_manager.get_storage_object("test-user-123", "bookmarks", "obj123")

        assert obj.id == "obj123"
        assert obj.payload == "test_payload"
        assert obj.modified == datetime.fromtimestamp(1234567890.12, tz=timezone.utc)
        assert obj.sortindex is None
        assert obj.ttl is None

    def test_create_or_update_collection_without_objects(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_timestamp_datetime,
        mock_get_current_timestamp,
    ):
        """Test creating collection without objects"""
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                    "name": "bookmarks",
                    "modified": Decimal(mock_timestamp),
                    "count": 0,
                    "usage": 0,
                },
            },
        )

        collection, batch_result = storage_manager.create_or_update_collection(
            "test-user-123", "bookmarks"
        )

        assert collection.name == "bookmarks"
        assert collection.modified == mock_timestamp_datetime
        assert collection.count == 0
        assert collection.usage == 0
        assert batch_result.success == []
        assert batch_result.failed == {}

    def test_create_or_update_collection_with_objects(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test creating collection with objects"""
        objects = [
            BasicStorageObject(
                id="obj1",
                payload="payload1",
                modified=datetime.fromtimestamp(mock_timestamp, tz=timezone.utc),
                sortindex=100,
                ttl=3600,
            ),
            BasicStorageObject(
                id="obj2",
                payload="payload2",
                modified=datetime.fromtimestamp(mock_timestamp, tz=timezone.utc),
            ),
        ]

        # Stub metadata put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                    "name": "bookmarks",
                    "modified": Decimal(datetime.fromtimestamp(mock_timestamp).timestamp()),
                    "count": 2,
                    "usage": len("payload1") + len("payload2"),
                },
            },
        )

        # Stub object 1 put - don't validate params due to dynamic expiry field
        dynamodb_stubber.add_response(
            "put_item",
            {},
            None,
        )

        # Stub object 2 put - don't validate params
        dynamodb_stubber.add_response(
            "put_item",
            {},
            None,
        )

        collection, batch_result = storage_manager.create_or_update_collection(
            "test-user-123", "bookmarks", objects
        )

        assert collection.name == "bookmarks"
        assert collection.count == 2
        assert batch_result.success == ["obj1", "obj2"]
        assert batch_result.failed == {}

    def test_update_collection(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test updating collection"""
        # Stub get_collection
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567880.00"},
                    "count": {"N": "1"},
                    "usage": {"N": "100"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        objects = [
            BasicStorageObject(
                id="obj1",
                payload="newpayload",
                modified=datetime.fromtimestamp(mock_timestamp, tz=timezone.utc),
            )
        ]

        # Stub object put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj1",
                    "id": "obj1",
                    "payload": "newpayload",
                    "modified": Decimal(datetime.fromtimestamp(mock_timestamp).timestamp()),
                    "sortindex": None,
                    "ttl": None,
                },
            },
        )

        # Stub metadata update
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                    "name": "bookmarks",
                    "modified": Decimal(datetime.fromtimestamp(mock_timestamp).timestamp()),
                    "count": 2,
                    "usage": 100 + len("newpayload"),
                },
            },
        )

        collection, batch_result = storage_manager.update_collection(
            "test-user-123", "bookmarks", objects
        )

        assert collection.name == "bookmarks"
        assert collection.count == 2
        assert batch_result.success == ["obj1"]

    def test_update_collection_not_found(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test updating non-existent collection raises error"""
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#nonexistent",
                    "SK": "METADATA",
                },
            },
        )

        objects = [
            BasicStorageObject(
                id="obj1",
                payload="payload",
                modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            )
        ]

        with pytest.raises(CollectionNotFoundException):
            storage_manager.update_collection("test-user-123", "nonexistent", objects)

    def test_delete_collection(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test deleting collection"""

        # Stub get_collection to verify it exists
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567880.00"},
                    "count": {"N": "1"},
                    "usage": {"N": "100"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        # Stub query to find all items
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "METADATA"},
                    },
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                    },
                ]
            },
            {
                "TableName": storage_table_name,
                "KeyConditionExpression": "PK = :pk",
                "ExpressionAttributeValues": {":pk": "USER#test-user-123#COLLECTION#bookmarks"},
            },
        )

        # Stub delete for metadata
        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        # Stub delete for object
        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj1",
                },
            },
        )

        modified = storage_manager.delete_collection("test-user-123", "bookmarks")
        assert modified == mock_timestamp

    def test_list_collections(self, storage_manager, dynamodb_stubber, storage_table_name):
        """Test listing all collections"""
        dynamodb_stubber.add_response(
            "scan",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "METADATA"},
                        "name": {"S": "bookmarks"},
                        "modified": {"N": "1234567890.12"},
                        "count": {"N": "5"},
                        "usage": {"N": "1024"},
                    },
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#history"},
                        "SK": {"S": "METADATA"},
                        "name": {"S": "history"},
                        "modified": {"N": "1234567891.00"},
                        "count": {"N": "10"},
                        "usage": {"N": "2048"},
                    },
                ]
            },
            {
                "TableName": storage_table_name,
                "FilterExpression": "begins_with(PK, :user_prefix) AND SK = :metadata",
                "ExpressionAttributeValues": {
                    ":user_prefix": "USER#test-user-123#COLLECTION#",
                    ":metadata": "METADATA",
                },
            },
        )

        collections = storage_manager.list_collections("test-user-123")

        assert len(collections) == 2
        assert collections[0].name == "bookmarks"
        assert collections[0].count == 5
        assert collections[1].name == "history"
        assert collections[1].count == 10

    def test_list_collections_empty(self, storage_manager, dynamodb_stubber, storage_table_name):
        """Test listing collections when none exist"""
        dynamodb_stubber.add_response(
            "scan",
            {"Items": []},
            {
                "TableName": storage_table_name,
                "FilterExpression": "begins_with(PK, :user_prefix) AND SK = :metadata",
                "ExpressionAttributeValues": {
                    ":user_prefix": "USER#test-user-123#COLLECTION#",
                    ":metadata": "METADATA",
                },
            },
        )

        collections = storage_manager.list_collections("test-user-123")
        assert collections == []

    def test_get_collection_objects(self, storage_manager, dynamodb_stubber, storage_table_name):
        """Test getting objects from collection"""
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                        "sortindex": {"N": "100"},
                    },
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj2"},
                        "id": {"S": "obj2"},
                        "payload": {"S": "payload2"},
                        "modified": {"N": "1234567890.00"},
                    },
                ]
            },
            {
                "TableName": storage_table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :obj_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": "USER#test-user-123#COLLECTION#bookmarks",
                    ":obj_prefix": "OBJECT#",
                },
            },
        )

        result = storage_manager.get_collection_objects("test-user-123", "bookmarks", limit=10)

        assert len(result["items"]) == 2
        assert result["items"][0].id == "obj1"  # sorted by newest first
        assert result["items"][1].id == "obj2"
        assert result["more"] is False
        assert result["last_modified"] == datetime.fromtimestamp(1234567891.00, tz=timezone.utc)

    def test_get_collection_objects_with_filters(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test getting objects with ID filter"""
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                    },
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj2"},
                        "id": {"S": "obj2"},
                        "payload": {"S": "payload2"},
                        "modified": {"N": "1234567890.00"},
                    },
                ]
            },
            {
                "TableName": storage_table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :obj_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": "USER#test-user-123#COLLECTION#bookmarks",
                    ":obj_prefix": "OBJECT#",
                },
            },
        )

        result = storage_manager.get_collection_objects("test-user-123", "bookmarks", ids="obj1")

        assert len(result["items"]) == 1
        assert result["items"][0].id == "obj1"

    def test_get_collection_objects_pagination(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test pagination of collection objects"""
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567893.00"},
                    },
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj2"},
                        "id": {"S": "obj2"},
                        "payload": {"S": "payload2"},
                        "modified": {"N": "1234567892.00"},
                    },
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj3"},
                        "id": {"S": "obj3"},
                        "payload": {"S": "payload3"},
                        "modified": {"N": "1234567891.00"},
                    },
                ]
            },
            {
                "TableName": storage_table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :obj_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": "USER#test-user-123#COLLECTION#bookmarks",
                    ":obj_prefix": "OBJECT#",
                },
            },
        )

        result = storage_manager.get_collection_objects(
            "test-user-123", "bookmarks", limit=2, offset=0
        )

        assert len(result["items"]) == 2
        assert result["more"] is True
        assert result["next_offset"] == 2

    def test_update_storage_object(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test updating storage object"""

        # Stub get_storage_object to verify it exists
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "old_payload"},
                    "modified": {"N": "1234567880.00"},
                    "sortindex": {"N": "100"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        # Stub put_item for update
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                    "id": "obj123",
                    "payload": "new_payload",
                    "modified": Decimal(datetime.fromtimestamp(mock_timestamp).timestamp()),
                    "sortindex": 100,
                    "ttl": None,
                },
            },
        )

        updated_obj = storage_manager.update_storage_object(
            "test-user-123", "bookmarks", "obj123", payload="new_payload"
        )

        assert updated_obj.id == "obj123"
        assert updated_obj.payload == "new_payload"
        assert updated_obj.modified == datetime.fromtimestamp(mock_timestamp, tz=timezone.utc)
        assert updated_obj.sortindex == 100

    def test_update_storage_object_not_found(
        self, storage_manager, dynamodb_stubber, storage_table_name, mock_get_current_timestamp
    ):
        """Test updating non-existent object creates it (PUT semantics)"""
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#nonexistent",
                },
            },
        )

        # Stub put_item for creating the new object
        dynamodb_stubber.add_response(
            "put_item",
            {},
            None,  # Don't validate params
        )

        obj = storage_manager.update_storage_object(
            "test-user-123", "bookmarks", "nonexistent", payload="new"
        )
        assert obj.id == "nonexistent"
        assert obj.payload == "new"

    def test_delete_storage_object(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test deleting storage object"""

        # Stub get_storage_object to verify it exists
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "payload"},
                    "modified": {"N": "1234567880.00"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        # Stub delete_item
        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        modified = storage_manager.delete_storage_object("test-user-123", "bookmarks", "obj123")
        assert modified == mock_timestamp

    def test_delete_storage_object_not_found(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test deleting non-existent object raises error"""
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#nonexistent",
                },
            },
        )

        with pytest.raises(StorageObjectNotFoundException):
            storage_manager.delete_storage_object("test-user-123", "bookmarks", "nonexistent")

    def test_get_collection_client_error(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test get_collection with ClientError for ResourceNotFoundException"""
        dynamodb_stubber.add_client_error(
            "get_item",
            service_error_code="ResourceNotFoundException",
            service_message="Table not found",
        )

        with pytest.raises(CollectionNotFoundException):
            storage_manager.get_collection("test-user-123", "bookmarks")

    def test_get_storage_object_client_error(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test get_storage_object with ClientError for ResourceNotFoundException"""
        dynamodb_stubber.add_client_error(
            "get_item",
            service_error_code="ResourceNotFoundException",
            service_message="Table not found",
        )

        with pytest.raises(StorageObjectNotFoundException):
            storage_manager.get_storage_object("test-user-123", "bookmarks", "obj123")

    def test_create_collection_with_failed_object(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test creating collection when some objects fail"""
        objects = [
            BasicStorageObject(
                id="obj1",
                payload="payload1",
                modified=datetime.fromtimestamp(mock_timestamp, tz=timezone.utc),
            )
        ]

        # Stub metadata put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                    "name": "bookmarks",
                    "modified": Decimal(datetime.fromtimestamp(mock_timestamp).timestamp()),
                    "count": 1,
                    "usage": len("payload1"),
                },
            },
        )

        # Stub object put with error
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ValidationException",
            service_message="Invalid item",
        )

        collection, batch_result = storage_manager.create_or_update_collection(
            "test-user-123", "bookmarks", objects
        )

        assert collection.name == "bookmarks"
        assert len(batch_result.success) == 0
        assert len(batch_result.failed) == 1
        assert "obj1" in batch_result.failed

    def test_update_collection_with_failed_object(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test updating collection when some objects fail"""
        # Stub get_collection
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567880.00"},
                    "count": {"N": "0"},
                    "usage": {"N": "0"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        objects = [
            BasicStorageObject(
                id="obj1",
                payload="newpayload",
                modified=datetime.fromtimestamp(mock_timestamp, tz=timezone.utc),
            )
        ]

        # Stub object put with error
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ValidationException",
            service_message="Invalid item",
        )

        # Stub metadata update
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                    "name": "bookmarks",
                    "modified": Decimal(datetime.fromtimestamp(mock_timestamp).timestamp()),
                    "count": 0,
                    "usage": 0,
                },
            },
        )

        collection, batch_result = storage_manager.update_collection(
            "test-user-123", "bookmarks", objects
        )

        assert len(batch_result.success) == 0
        assert len(batch_result.failed) == 1

    def test_get_collection_objects_with_newer_filter(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test getting objects with newer timestamp filter"""
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                    },
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj2"},
                        "id": {"S": "obj2"},
                        "payload": {"S": "payload2"},
                        "modified": {"N": "1234567889.00"},
                    },
                ]
            },
            {
                "TableName": storage_table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :obj_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": "USER#test-user-123#COLLECTION#bookmarks",
                    ":obj_prefix": "OBJECT#",
                },
            },
        )

        result = storage_manager.get_collection_objects(
            "test-user-123", "bookmarks", newer=1234567890.00
        )

        assert len(result["items"]) == 1
        assert result["items"][0].id == "obj1"

    def test_get_collection_objects_with_older_filter(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test getting objects with older timestamp filter"""
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                    },
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj2"},
                        "id": {"S": "obj2"},
                        "payload": {"S": "payload2"},
                        "modified": {"N": "1234567889.00"},
                    },
                ]
            },
            {
                "TableName": storage_table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :obj_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": "USER#test-user-123#COLLECTION#bookmarks",
                    ":obj_prefix": "OBJECT#",
                },
            },
        )

        result = storage_manager.get_collection_objects(
            "test-user-123", "bookmarks", older=1234567890.00
        )

        assert len(result["items"]) == 1
        assert result["items"][0].id == "obj2"

    def test_get_collection_objects_sort_oldest(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test getting objects sorted by oldest first"""
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                    },
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj2"},
                        "id": {"S": "obj2"},
                        "payload": {"S": "payload2"},
                        "modified": {"N": "1234567890.00"},
                    },
                ]
            },
            {
                "TableName": storage_table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :obj_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": "USER#test-user-123#COLLECTION#bookmarks",
                    ":obj_prefix": "OBJECT#",
                },
            },
        )

        result = storage_manager.get_collection_objects("test-user-123", "bookmarks", sort="oldest")

        assert result["items"][0].id == "obj2"  # oldest first
        assert result["items"][1].id == "obj1"

    def test_get_collection_objects_sort_index(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test getting objects sorted by sortindex"""
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                        "sortindex": {"N": "100"},
                    },
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj2"},
                        "id": {"S": "obj2"},
                        "payload": {"S": "payload2"},
                        "modified": {"N": "1234567890.00"},
                        "sortindex": {"N": "200"},
                    },
                ]
            },
            {
                "TableName": storage_table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :obj_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": "USER#test-user-123#COLLECTION#bookmarks",
                    ":obj_prefix": "OBJECT#",
                },
            },
        )

        result = storage_manager.get_collection_objects("test-user-123", "bookmarks", sort="index")

        assert result["items"][0].id == "obj2"  # higher sortindex first
        assert result["items"][1].id == "obj1"

    def test_update_storage_object_with_all_fields(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test updating storage object with all optional fields"""
        # Stub get_storage_object to verify it exists
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "old_payload"},
                    "modified": {"N": "1234567880.00"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        # Stub put_item for update - don't check exact params since expiry is dynamic
        dynamodb_stubber.add_response(
            "put_item",
            {},
            None,  # Don't validate params due to dynamic expiry field
        )

        updated_obj = storage_manager.update_storage_object(
            "test-user-123", "bookmarks", "obj123", payload="new_payload", sortindex=150, ttl=7200
        )

        assert updated_obj.payload == "new_payload"
        assert updated_obj.sortindex == 150
        assert updated_obj.ttl == 7200

    def test_get_collection_client_error_other(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test get_collection with other ClientError"""
        dynamodb_stubber.add_client_error(
            "get_item",
            service_error_code="AccessDeniedException",
            service_message="Access denied",
        )

        with pytest.raises(Exception):  # Should raise the original ClientError
            storage_manager.get_collection("test-user-123", "bookmarks")

    def test_get_storage_object_client_error_other(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test get_storage_object with other ClientError"""
        dynamodb_stubber.add_client_error(
            "get_item",
            service_error_code="AccessDeniedException",
            service_message="Access denied",
        )

        with pytest.raises(Exception):  # Should raise the original ClientError
            storage_manager.get_storage_object("test-user-123", "bookmarks", "obj123")

    def test_get_collection_objects_empty_result(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test getting objects when collection is empty"""
        dynamodb_stubber.add_response(
            "query",
            {"Items": []},
            {
                "TableName": storage_table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :obj_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": "USER#test-user-123#COLLECTION#bookmarks",
                    ":obj_prefix": "OBJECT#",
                },
            },
        )

        result = storage_manager.get_collection_objects("test-user-123", "bookmarks")

        assert len(result["items"]) == 0
        assert result["more"] is False
        assert result["last_modified"] == datetime.fromtimestamp(0.0, tz=timezone.utc)

    def test_update_collection_with_mixed_success_fail(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test updating collection with some objects succeeding and some failing"""
        # Stub get_collection
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567880.00"},
                    "count": {"N": "0"},
                    "usage": {"N": "0"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        objects = [
            BasicStorageObject(
                id="obj1",
                payload="payload1",
                modified=datetime.fromtimestamp(mock_timestamp, tz=timezone.utc),
            ),
            BasicStorageObject(
                id="obj2",
                payload="payload2",
                modified=datetime.fromtimestamp(mock_timestamp, tz=timezone.utc),
            ),
        ]

        # Stub object 1 put (success)
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj1",
                    "id": "obj1",
                    "payload": "payload1",
                    "modified": Decimal(datetime.fromtimestamp(mock_timestamp).timestamp()),
                    "sortindex": None,
                    "ttl": None,
                },
            },
        )

        # Stub object 2 put (failure)
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ValidationException",
            service_message="Invalid item",
        )

        # Stub metadata update
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                    "name": "bookmarks",
                    "modified": Decimal(datetime.fromtimestamp(mock_timestamp).timestamp()),
                    "count": 1,
                    "usage": len("payload1"),
                },
            },
        )

        collection, batch_result = storage_manager.update_collection(
            "test-user-123", "bookmarks", objects
        )

        assert len(batch_result.success) == 1
        assert "obj1" in batch_result.success
        assert len(batch_result.failed) == 1
        assert "obj2" in batch_result.failed

    def test_update_collection_with_sortindex_and_ttl(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test updating collection with objects that have sortindex and ttl"""
        # Stub get_collection
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567880.00"},
                    "count": {"N": "0"},
                    "usage": {"N": "0"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        objects = [
            BasicStorageObject(
                id="obj1",
                payload="payload1",
                modified=datetime.fromtimestamp(mock_timestamp, tz=timezone.utc),
                sortindex=150,
                ttl=7200,
            )
        ]

        # Stub object put with sortindex and ttl - don't validate params due to dynamic expiry
        dynamodb_stubber.add_response(
            "put_item",
            {},
            None,
        )

        # Stub metadata update
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                    "name": "bookmarks",
                    "modified": Decimal(datetime.fromtimestamp(mock_timestamp).timestamp()),
                    "count": 1,
                    "usage": len("payload1"),
                },
            },
        )

        collection, batch_result = storage_manager.update_collection(
            "test-user-123", "bookmarks", objects
        )

        assert len(batch_result.success) == 1

    def test_update_storage_object_preserves_ttl(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test updating storage object preserves ttl when not provided"""
        # Stub get_storage_object with ttl
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "old_payload"},
                    "modified": {"N": "1234567880.00"},
                    "ttl": {"N": "3600"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        # Stub put_item - don't validate params due to dynamic expiry
        dynamodb_stubber.add_response(
            "put_item",
            {},
            None,
        )

        updated_obj = storage_manager.update_storage_object("test-user-123", "bookmarks", "obj123")

        assert updated_obj.ttl == 3600

    def test_update_storage_object_without_sortindex(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test updating object without providing sortindex to test branch"""
        # Stub get_storage_object - object without sortindex but with ttl
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "old_payload"},
                    "modified": {"N": "1234567880.00"},
                    "ttl": {"N": "3600"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        # Stub put_item - don't validate params due to dynamic expiry
        dynamodb_stubber.add_response(
            "put_item",
            {},
            None,
        )

        updated_obj = storage_manager.update_storage_object("test-user-123", "bookmarks", "obj123")

        assert updated_obj.sortindex is None
        assert updated_obj.ttl == 3600

    def test_get_collection_objects_invalid_sort(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test getting objects with invalid sort parameter (should not sort)"""
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                    },
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj2"},
                        "id": {"S": "obj2"},
                        "payload": {"S": "payload2"},
                        "modified": {"N": "1234567890.00"},
                    },
                ]
            },
            {
                "TableName": storage_table_name,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :obj_prefix)",
                "ExpressionAttributeValues": {
                    ":pk": "USER#test-user-123#COLLECTION#bookmarks",
                    ":obj_prefix": "OBJECT#",
                },
            },
        )

        result = storage_manager.get_collection_objects(
            "test-user-123", "bookmarks", sort="invalid"
        )

        assert len(result["items"]) == 2
        assert result["last_modified"] == datetime.fromtimestamp(1234567891.00, tz=timezone.utc)

    def test_update_storage_object_with_only_sortindex(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test updating object with only sortindex to test branch"""
        # Stub get_storage_object
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "old_payload"},
                    "modified": {"N": "1234567880.00"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        # Stub put_item
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                    "id": "obj123",
                    "payload": "old_payload",
                    "modified": Decimal(datetime.fromtimestamp(mock_timestamp).timestamp()),
                    "sortindex": 200,
                    "ttl": None,
                },
            },
        )

        updated_obj = storage_manager.update_storage_object(
            "test-user-123", "bookmarks", "obj123", sortindex=200
        )

        assert updated_obj.sortindex == 200
        assert updated_obj.ttl is None

    def test_update_storage_object_with_sortindex_no_ttl(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test updating object with sortindex but no ttl to cover branch"""
        # Stub get_storage_object - has sortindex and ttl
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "old_payload"},
                    "modified": {"N": "1234567880.00"},
                    "sortindex": {"N": "100"},
                    "ttl": {"N": "3600"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        # Stub put_item - don't validate params due to dynamic expiry
        dynamodb_stubber.add_response(
            "put_item",
            {},
            None,
        )

        updated_obj = storage_manager.update_storage_object(
            "test-user-123", "bookmarks", "obj123", payload="updated_payload"
        )

        assert updated_obj.sortindex == 100
        assert updated_obj.ttl == 3600

    def test_update_storage_object_sortindex_without_ttl(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test updating object that has sortindex but no ttl - covering branch 401->405"""
        # Stub get_storage_object - object WITH sortindex but NO ttl
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "old_payload"},
                    "modified": {"N": "1234567880.00"},
                    "sortindex": {"N": "100"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        # Stub put_item - sortindex present, ttl absent
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                    "id": "obj123",
                    "payload": "old_payload",
                    "modified": Decimal(datetime.fromtimestamp(mock_timestamp).timestamp()),
                    "sortindex": 100,
                    "ttl": None,
                },
            },
        )

        updated_obj = storage_manager.update_storage_object("test-user-123", "bookmarks", "obj123")

        assert updated_obj.sortindex == 100
        assert updated_obj.ttl is None

    def test_create_collection_batch_limit_exceeded(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test creating collection with too many objects raises ServerLimitExceededException"""
        from src.shared.exceptions import ServerLimitExceededException

        # Create 101 objects (exceeds MAX_POST_RECORDS=100)
        objects = [
            BasicStorageObject(
                id=f"obj{i}",
                payload="x",
                modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            )
            for i in range(101)
        ]

        with pytest.raises(ServerLimitExceededException):
            storage_manager.create_or_update_collection("test-user-123", "bookmarks", objects)

    def test_create_collection_batch_size_exceeded(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test creating collection with too large payload raises ServerLimitExceededException"""
        from src.shared.exceptions import ServerLimitExceededException

        # Create object with payload > 2MB
        large_payload = "x" * (2 * 1024 * 1024 + 1)
        objects = [
            BasicStorageObject(
                id="obj1",
                payload=large_payload,
                modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            )
        ]

        with pytest.raises(ServerLimitExceededException):
            storage_manager.create_or_update_collection("test-user-123", "bookmarks", objects)

    def test_create_collection_precondition_create_only_fails(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_get_current_timestamp,
    ):
        """Test create-only mode fails when collection exists"""
        from src.shared.exceptions import PreconditionFailedException

        # Stub get_collection to return existing collection
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567890.12"},
                    "count": {"N": "5"},
                    "usage": {"N": "1024"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        with pytest.raises(PreconditionFailedException):
            storage_manager.create_or_update_collection(
                "test-user-123", "bookmarks", [], if_unmodified_since=0
            )

    def test_create_collection_precondition_modified_since(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_get_current_timestamp,
    ):
        """Test precondition fails when collection modified since timestamp"""
        from src.shared.exceptions import PreconditionFailedException

        # Stub get_collection to return collection modified after the precondition timestamp
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567900.00"},  # Modified after precondition
                    "count": {"N": "5"},
                    "usage": {"N": "1024"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        with pytest.raises(PreconditionFailedException):
            storage_manager.create_or_update_collection(
                "test-user-123", "bookmarks", [], if_unmodified_since=1234567890.00
            )

    def test_update_collection_batch_limit_exceeded(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test updating collection with too many objects raises ServerLimitExceededException"""
        from src.shared.exceptions import ServerLimitExceededException

        # Create 101 objects (exceeds MAX_POST_RECORDS=100)
        objects = [
            BasicStorageObject(
                id=f"obj{i}",
                payload="x",
                modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            )
            for i in range(101)
        ]

        with pytest.raises(ServerLimitExceededException):
            storage_manager.update_collection("test-user-123", "bookmarks", objects)

    def test_update_collection_batch_size_exceeded(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test updating collection with too large payload raises ServerLimitExceededException"""
        from src.shared.exceptions import ServerLimitExceededException

        # Create object with payload > 2MB
        large_payload = "x" * (2 * 1024 * 1024 + 1)
        objects = [
            BasicStorageObject(
                id="obj1",
                payload=large_payload,
                modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            )
        ]

        with pytest.raises(ServerLimitExceededException):
            storage_manager.update_collection("test-user-123", "bookmarks", objects)

    def test_update_collection_precondition_modified_since(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_get_current_timestamp,
    ):
        """Test update precondition fails when collection modified since timestamp"""
        from src.shared.exceptions import PreconditionFailedException

        # Stub get_collection to return collection modified after the precondition timestamp
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567900.00"},  # Modified after precondition
                    "count": {"N": "5"},
                    "usage": {"N": "1024"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        with pytest.raises(PreconditionFailedException):
            storage_manager.update_collection(
                "test-user-123", "bookmarks", [], if_unmodified_since=1234567890.00
            )

    def test_get_collection_objects_ids_limit_exceeded(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test getting objects with too many IDs raises ValidationException"""
        from src.shared.exceptions import ValidationException

        # Create comma-separated list of 101 IDs
        ids = ",".join([f"obj{i}" for i in range(101)])

        with pytest.raises(ValidationException):
            storage_manager.get_collection_objects("test-user-123", "bookmarks", ids=ids)

    def test_update_storage_object_precondition_create_only_fails(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_get_current_timestamp,
    ):
        """Test create-only mode fails when object exists"""
        from src.shared.exceptions import PreconditionFailedException

        # Stub get_storage_object to return existing object
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "existing_payload"},
                    "modified": {"N": "1234567890.12"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        with pytest.raises(PreconditionFailedException):
            storage_manager.update_storage_object(
                "test-user-123",
                "bookmarks",
                "obj123",
                payload="new",
                if_unmodified_since=0,
            )

    def test_update_storage_object_precondition_modified_since(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_get_current_timestamp,
    ):
        """Test update precondition fails when object modified since timestamp"""
        from src.shared.exceptions import PreconditionFailedException

        # Stub get_storage_object to return object modified after the precondition timestamp
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "existing_payload"},
                    "modified": {"N": "1234567900.00"},  # Modified after precondition
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        with pytest.raises(PreconditionFailedException):
            storage_manager.update_storage_object(
                "test-user-123",
                "bookmarks",
                "obj123",
                payload="new",
                if_unmodified_since=1234567890.00,
            )

    def test_update_storage_object_precondition_nonexistent_object(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_get_current_timestamp,
    ):
        """Test precondition fails when checking non-existent object with non-zero timestamp"""
        from src.shared.exceptions import PreconditionFailedException

        # Stub get_storage_object to return empty (object doesn't exist)
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#nonexistent",
                },
            },
        )

        with pytest.raises(PreconditionFailedException):
            storage_manager.update_storage_object(
                "test-user-123",
                "bookmarks",
                "nonexistent",
                payload="new",
                if_unmodified_since=1234567890.00,
            )

    def test_delete_collection_objects(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test batch deleting multiple objects"""
        # Stub get_collection to verify collection exists
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567890.00"},
                    "count": {"N": "5"},
                    "usage": {"N": "1024"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        # Stub delete_item for each object
        dynamodb_stubber.add_response("delete_item", {}, None)
        dynamodb_stubber.add_response("delete_item", {}, None)

        # Stub get_collection again for updating metadata
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567890.00"},
                    "count": {"N": "3"},
                    "usage": {"N": "512"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        # Stub put_item for metadata update
        dynamodb_stubber.add_response("put_item", {}, None)

        modified = storage_manager.delete_collection_objects(
            "test-user-123", "bookmarks", ["obj1", "obj2"]
        )

        assert modified == mock_timestamp

    def test_delete_collection_objects_limit_exceeded(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test batch delete with too many IDs raises ValidationException"""
        from src.shared.exceptions import ValidationException

        # Create list of 101 IDs
        ids = [f"obj{i}" for i in range(101)]

        with pytest.raises(ValidationException):
            storage_manager.delete_collection_objects("test-user-123", "bookmarks", ids)

    def test_delete_collection_objects_with_error(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test batch delete continues when individual delete fails"""
        # Stub get_collection to verify collection exists
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567890.00"},
                    "count": {"N": "5"},
                    "usage": {"N": "1024"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        # First delete fails
        dynamodb_stubber.add_client_error(
            "delete_item",
            service_error_code="ValidationException",
            service_message="Delete failed",
        )

        # Second delete succeeds
        dynamodb_stubber.add_response("delete_item", {}, None)

        # Stub get_collection again for updating metadata
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567890.00"},
                    "count": {"N": "4"},
                    "usage": {"N": "800"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        # Stub put_item for metadata update
        dynamodb_stubber.add_response("put_item", {}, None)

        # Should complete without raising, even though first delete failed
        modified = storage_manager.delete_collection_objects(
            "test-user-123", "bookmarks", ["obj1", "obj2"]
        )

        assert modified == mock_timestamp

    def test_delete_all_storage(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test deleting all storage for a user"""
        # Stub scan to return items
        dynamodb_stubber.add_response(
            "scan",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "METADATA"},
                    },
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                    },
                ]
            },
            None,
        )

        # Stub delete_item for each item
        dynamodb_stubber.add_response("delete_item", {}, None)
        dynamodb_stubber.add_response("delete_item", {}, None)

        modified = storage_manager.delete_all_storage("test-user-123")

        assert modified == mock_timestamp

    def test_delete_all_storage_with_pagination(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test deleting all storage with pagination"""
        # Stub first scan page with LastEvaluatedKey
        dynamodb_stubber.add_response(
            "scan",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "METADATA"},
                    },
                ],
                "LastEvaluatedKey": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                },
            },
            None,
        )

        # Stub delete_item for first page
        dynamodb_stubber.add_response("delete_item", {}, None)

        # Stub second scan page (no more items)
        dynamodb_stubber.add_response(
            "scan",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#history"},
                        "SK": {"S": "METADATA"},
                    },
                ]
            },
            None,
        )

        # Stub delete_item for second page
        dynamodb_stubber.add_response("delete_item", {}, None)

        modified = storage_manager.delete_all_storage("test-user-123")

        assert modified == mock_timestamp

    def test_get_quota(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """Test getting quota information"""
        # list_collections uses scan
        dynamodb_stubber.add_response(
            "scan",
            {
                "Items": [
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                        "SK": {"S": "METADATA"},
                        "name": {"S": "bookmarks"},
                        "modified": {"N": "1234567890.00"},
                        "count": {"N": "5"},
                        "usage": {"N": "1024"},
                    },
                    {
                        "PK": {"S": "USER#test-user-123#COLLECTION#history"},
                        "SK": {"S": "METADATA"},
                        "name": {"S": "history"},
                        "modified": {"N": "1234567880.00"},
                        "count": {"N": "10"},
                        "usage": {"N": "2048"},
                    },
                ]
            },
            None,
        )

        usage_kb, quota_kb = storage_manager.get_quota("test-user-123")

        assert usage_kb == (1024 + 2048) / 1024.0
        assert quota_kb is None  # Unlimited

    def test_create_collection_precondition_passes(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test precondition passes when collection not modified since timestamp"""
        # Stub get_collection to return collection modified before the precondition timestamp
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567880.00"},  # Modified before precondition
                    "count": {"N": "5"},
                    "usage": {"N": "1024"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        # Stub put_item for metadata update
        dynamodb_stubber.add_response("put_item", {}, None)

        collection, batch_result = storage_manager.create_or_update_collection(
            "test-user-123", "bookmarks", [], if_unmodified_since=1234567890.00
        )

        assert collection.name == "bookmarks"

    def test_update_collection_precondition_passes(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test update precondition passes when collection not modified since timestamp"""
        # Stub get_collection to return collection modified before the precondition timestamp
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567880.00"},  # Modified before precondition
                    "count": {"N": "5"},
                    "usage": {"N": "1024"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "METADATA",
                },
            },
        )

        # Stub put_item for metadata update
        dynamodb_stubber.add_response("put_item", {}, None)

        collection, batch_result = storage_manager.update_collection(
            "test-user-123", "bookmarks", [], if_unmodified_since=1234567890.00
        )

        assert collection.name == "bookmarks"

    def test_update_storage_object_precondition_passes(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test update precondition passes when object not modified since timestamp"""
        # Stub get_storage_object to return object modified before the precondition timestamp
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "USER#test-user-123#COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "existing_payload"},
                    "modified": {"N": "1234567880.00"},  # Modified before precondition
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": "USER#test-user-123#COLLECTION#bookmarks",
                    "SK": "OBJECT#obj123",
                },
            },
        )

        # Stub put_item for update
        dynamodb_stubber.add_response("put_item", {}, None)

        obj = storage_manager.update_storage_object(
            "test-user-123",
            "bookmarks",
            "obj123",
            payload="new_payload",
            if_unmodified_since=1234567890.00,
        )

        assert obj.payload == "new_payload"
