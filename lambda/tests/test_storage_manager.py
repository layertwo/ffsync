"""Unit tests for StorageManager with DynamoDB stubber"""

from unittest.mock import patch

import pytest

from src.services.storage_manager import StorageManager
from src.shared.exceptions import (
    CollectionNotFoundException,
    StorageObjectNotFoundException,
)
from src.shared.models import BasicStorageObject


@pytest.fixture
def mock_timestamp():
    return 1234567890.12


@pytest.fixture
def mock_get_current_timestamp(mock_timestamp):
    with patch("src.services.storage_manager.get_current_timestamp", return_value=mock_timestamp):
        yield


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
                    "PK": {"S": "COLLECTION#bookmarks"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                },
            },
        )

        collection = storage_manager.get_collection("bookmarks")

        assert collection.name == "bookmarks"
        assert collection.modified == 1234567890.12
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
                    "PK": {"S": "COLLECTION#nonexistent"},
                    "SK": {"S": "METADATA"},
                },
            },
        )

        with pytest.raises(CollectionNotFoundException):
            storage_manager.get_collection("nonexistent")

    def test_get_storage_object_success(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test successful storage object retrieval"""
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "COLLECTION#bookmarks"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                },
            },
        )

        obj = storage_manager.get_storage_object("bookmarks", "obj123")

        assert obj.id == "obj123"
        assert obj.payload == "test_payload"
        assert obj.modified == 1234567890.12
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#nonexistent"},
                },
            },
        )

        with pytest.raises(StorageObjectNotFoundException):
            storage_manager.get_storage_object("bookmarks", "nonexistent")

    def test_get_storage_object_without_optional_fields(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test retrieval of storage object without sortindex and ttl"""
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "test_payload"},
                    "modified": {"N": "1234567890.12"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                },
            },
        )

        obj = storage_manager.get_storage_object("bookmarks", "obj123")

        assert obj.id == "obj123"
        assert obj.payload == "test_payload"
        assert obj.modified == 1234567890.12
        assert obj.sortindex is None
        assert obj.ttl is None

    def test_create_or_update_collection_without_objects(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test creating collection without objects"""
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": str(mock_timestamp)},
                    "count": {"N": "0"},
                    "usage": {"N": "0"},
                },
            },
        )

        collection, batch_result = storage_manager.create_or_update_collection("bookmarks")

        assert collection.name == "bookmarks"
        assert collection.modified == mock_timestamp
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
                modified=mock_timestamp,
                sortindex=100,
                ttl=3600,
            ),
            BasicStorageObject(id="obj2", payload="payload2", modified=mock_timestamp),
        ]

        # Stub metadata put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": str(mock_timestamp)},
                    "count": {"N": "2"},
                    "usage": {"N": str(len("payload1") + len("payload2"))},
                },
            },
        )

        # Stub object 1 put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj1"},
                    "id": {"S": "obj1"},
                    "payload": {"S": "payload1"},
                    "modified": {"N": str(mock_timestamp)},
                    "sortindex": {"N": "100"},
                    "ttl": {"N": "3600"},
                },
            },
        )

        # Stub object 2 put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj2"},
                    "id": {"S": "obj2"},
                    "payload": {"S": "payload2"},
                    "modified": {"N": str(mock_timestamp)},
                },
            },
        )

        collection, batch_result = storage_manager.create_or_update_collection("bookmarks", objects)

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
                    "PK": {"S": "COLLECTION#bookmarks"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                },
            },
        )

        objects = [BasicStorageObject(id="obj1", payload="newpayload", modified=mock_timestamp)]

        # Stub object put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj1"},
                    "id": {"S": "obj1"},
                    "payload": {"S": "newpayload"},
                    "modified": {"N": str(mock_timestamp)},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": str(mock_timestamp)},
                    "count": {"N": "2"},
                    "usage": {"N": str(100 + len("newpayload"))},
                },
            },
        )

        collection, batch_result = storage_manager.update_collection("bookmarks", objects)

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
                    "PK": {"S": "COLLECTION#nonexistent"},
                    "SK": {"S": "METADATA"},
                },
            },
        )

        objects = [BasicStorageObject(id="obj1", payload="payload", modified=mock_timestamp)]

        with pytest.raises(CollectionNotFoundException):
            storage_manager.update_collection("nonexistent", objects)

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
                    "PK": {"S": "COLLECTION#bookmarks"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                },
            },
        )

        # Stub query to find all items
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
                        "SK": {"S": "METADATA"},
                    },
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                    },
                ]
            },
            {
                "TableName": storage_table_name,
                "KeyConditionExpression": "PK = :pk",
                "ExpressionAttributeValues": {":pk": {"S": "COLLECTION#bookmarks"}},
            },
        )

        # Stub delete for metadata
        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj1"},
                },
            },
        )

        modified = storage_manager.delete_collection("bookmarks")
        assert modified == mock_timestamp

    def test_list_collections(self, storage_manager, dynamodb_stubber, storage_table_name):
        """Test listing all collections"""
        dynamodb_stubber.add_response(
            "scan",
            {
                "Items": [
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
                        "SK": {"S": "METADATA"},
                        "name": {"S": "bookmarks"},
                        "modified": {"N": "1234567890.12"},
                        "count": {"N": "5"},
                        "usage": {"N": "1024"},
                    },
                    {
                        "PK": {"S": "COLLECTION#history"},
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
                "FilterExpression": "SK = :metadata",
                "ExpressionAttributeValues": {":metadata": {"S": "METADATA"}},
            },
        )

        collections = storage_manager.list_collections()

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
                "FilterExpression": "SK = :metadata",
                "ExpressionAttributeValues": {":metadata": {"S": "METADATA"}},
            },
        )

        collections = storage_manager.list_collections()
        assert collections == []

    def test_get_collection_objects(self, storage_manager, dynamodb_stubber, storage_table_name):
        """Test getting objects from collection"""
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                        "sortindex": {"N": "100"},
                    },
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
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
                    ":pk": {"S": "COLLECTION#bookmarks"},
                    ":obj_prefix": {"S": "OBJECT#"},
                },
            },
        )

        result = storage_manager.get_collection_objects("bookmarks", limit=10)

        assert len(result["items"]) == 2
        assert result["items"][0].id == "obj1"  # sorted by newest first
        assert result["items"][1].id == "obj2"
        assert result["more"] is False
        assert result["last_modified"] == 1234567891.00

    def test_get_collection_objects_with_filters(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test getting objects with ID filter"""
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                    },
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
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
                    ":pk": {"S": "COLLECTION#bookmarks"},
                    ":obj_prefix": {"S": "OBJECT#"},
                },
            },
        )

        result = storage_manager.get_collection_objects("bookmarks", ids="obj1")

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
                        "PK": {"S": "COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567893.00"},
                    },
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj2"},
                        "id": {"S": "obj2"},
                        "payload": {"S": "payload2"},
                        "modified": {"N": "1234567892.00"},
                    },
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
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
                    ":pk": {"S": "COLLECTION#bookmarks"},
                    ":obj_prefix": {"S": "OBJECT#"},
                },
            },
        )

        result = storage_manager.get_collection_objects("bookmarks", limit=2, offset=0)

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
                    "PK": {"S": "COLLECTION#bookmarks"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "new_payload"},
                    "modified": {"N": str(mock_timestamp)},
                    "sortindex": {"N": "100"},
                },
            },
        )

        updated_obj = storage_manager.update_storage_object(
            "bookmarks", "obj123", payload="new_payload"
        )

        assert updated_obj.id == "obj123"
        assert updated_obj.payload == "new_payload"
        assert updated_obj.modified == mock_timestamp
        assert updated_obj.sortindex == 100

    def test_update_storage_object_not_found(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test updating non-existent object raises error"""
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#nonexistent"},
                },
            },
        )

        with pytest.raises(StorageObjectNotFoundException):
            storage_manager.update_storage_object("bookmarks", "nonexistent", payload="new")

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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "payload"},
                    "modified": {"N": "1234567880.00"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                },
            },
        )

        modified = storage_manager.delete_storage_object("bookmarks", "obj123")
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#nonexistent"},
                },
            },
        )

        with pytest.raises(StorageObjectNotFoundException):
            storage_manager.delete_storage_object("bookmarks", "nonexistent")

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
            storage_manager.get_collection("bookmarks")

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
            storage_manager.get_storage_object("bookmarks", "obj123")

    def test_create_collection_with_failed_object(
        self,
        storage_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test creating collection when some objects fail"""
        objects = [BasicStorageObject(id="obj1", payload="payload1", modified=mock_timestamp)]

        # Stub metadata put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": str(mock_timestamp)},
                    "count": {"N": "1"},
                    "usage": {"N": str(len("payload1"))},
                },
            },
        )

        # Stub object put with error
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ValidationException",
            service_message="Invalid item",
        )

        collection, batch_result = storage_manager.create_or_update_collection("bookmarks", objects)

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
                    "PK": {"S": "COLLECTION#bookmarks"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                },
            },
        )

        objects = [BasicStorageObject(id="obj1", payload="newpayload", modified=mock_timestamp)]

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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": str(mock_timestamp)},
                    "count": {"N": "0"},
                    "usage": {"N": "0"},
                },
            },
        )

        collection, batch_result = storage_manager.update_collection("bookmarks", objects)

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
                        "PK": {"S": "COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                    },
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
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
                    ":pk": {"S": "COLLECTION#bookmarks"},
                    ":obj_prefix": {"S": "OBJECT#"},
                },
            },
        )

        result = storage_manager.get_collection_objects("bookmarks", newer=1234567890.00)

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
                        "PK": {"S": "COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                    },
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
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
                    ":pk": {"S": "COLLECTION#bookmarks"},
                    ":obj_prefix": {"S": "OBJECT#"},
                },
            },
        )

        result = storage_manager.get_collection_objects("bookmarks", older=1234567890.00)

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
                        "PK": {"S": "COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                    },
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
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
                    ":pk": {"S": "COLLECTION#bookmarks"},
                    ":obj_prefix": {"S": "OBJECT#"},
                },
            },
        )

        result = storage_manager.get_collection_objects("bookmarks", sort="oldest")

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
                        "PK": {"S": "COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                        "sortindex": {"N": "100"},
                    },
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
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
                    ":pk": {"S": "COLLECTION#bookmarks"},
                    ":obj_prefix": {"S": "OBJECT#"},
                },
            },
        )

        result = storage_manager.get_collection_objects("bookmarks", sort="index")

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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "old_payload"},
                    "modified": {"N": "1234567880.00"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "new_payload"},
                    "modified": {"N": str(mock_timestamp)},
                    "sortindex": {"N": "150"},
                    "ttl": {"N": "7200"},
                },
            },
        )

        updated_obj = storage_manager.update_storage_object(
            "bookmarks", "obj123", payload="new_payload", sortindex=150, ttl=7200
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
            storage_manager.get_collection("bookmarks")

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
            storage_manager.get_storage_object("bookmarks", "obj123")

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
                    ":pk": {"S": "COLLECTION#bookmarks"},
                    ":obj_prefix": {"S": "OBJECT#"},
                },
            },
        )

        result = storage_manager.get_collection_objects("bookmarks")

        assert len(result["items"]) == 0
        assert result["more"] is False
        assert result["last_modified"] == 0.0

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
                    "PK": {"S": "COLLECTION#bookmarks"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                },
            },
        )

        objects = [
            BasicStorageObject(id="obj1", payload="payload1", modified=mock_timestamp),
            BasicStorageObject(id="obj2", payload="payload2", modified=mock_timestamp),
        ]

        # Stub object 1 put (success)
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj1"},
                    "id": {"S": "obj1"},
                    "payload": {"S": "payload1"},
                    "modified": {"N": str(mock_timestamp)},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": str(mock_timestamp)},
                    "count": {"N": "1"},
                    "usage": {"N": str(len("payload1"))},
                },
            },
        )

        collection, batch_result = storage_manager.update_collection("bookmarks", objects)

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
                    "PK": {"S": "COLLECTION#bookmarks"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                },
            },
        )

        objects = [
            BasicStorageObject(
                id="obj1",
                payload="payload1",
                modified=mock_timestamp,
                sortindex=150,
                ttl=7200,
            )
        ]

        # Stub object put with sortindex and ttl
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj1"},
                    "id": {"S": "obj1"},
                    "payload": {"S": "payload1"},
                    "modified": {"N": str(mock_timestamp)},
                    "sortindex": {"N": "150"},
                    "ttl": {"N": "7200"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": str(mock_timestamp)},
                    "count": {"N": "1"},
                    "usage": {"N": str(len("payload1"))},
                },
            },
        )

        collection, batch_result = storage_manager.update_collection("bookmarks", objects)

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
                    "PK": {"S": "COLLECTION#bookmarks"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "old_payload"},
                    "modified": {"N": str(mock_timestamp)},
                    "ttl": {"N": "3600"},
                },
            },
        )

        updated_obj = storage_manager.update_storage_object("bookmarks", "obj123")

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
                    "PK": {"S": "COLLECTION#bookmarks"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                },
            },
        )

        # Stub put_item - no sortindex in result
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "old_payload"},
                    "modified": {"N": str(mock_timestamp)},
                    "ttl": {"N": "3600"},
                },
            },
        )

        updated_obj = storage_manager.update_storage_object("bookmarks", "obj123")

        assert updated_obj.sortindex is None
        assert updated_obj.ttl == 3600

    def test_serialize_item_method(self, storage_manager):
        """Test _serialize_item helper method"""
        data = {
            "name": "test",
            "count": 5,
            "none_value": None,
        }

        result = storage_manager._serialize_item(data)

        assert "name" in result
        assert "count" in result
        assert "none_value" not in result  # None values are skipped

    def test_get_collection_objects_invalid_sort(
        self, storage_manager, dynamodb_stubber, storage_table_name
    ):
        """Test getting objects with invalid sort parameter (should not sort)"""
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
                        "SK": {"S": "OBJECT#obj1"},
                        "id": {"S": "obj1"},
                        "payload": {"S": "payload1"},
                        "modified": {"N": "1234567891.00"},
                    },
                    {
                        "PK": {"S": "COLLECTION#bookmarks"},
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
                    ":pk": {"S": "COLLECTION#bookmarks"},
                    ":obj_prefix": {"S": "OBJECT#"},
                },
            },
        )

        result = storage_manager.get_collection_objects("bookmarks", sort="invalid")

        assert len(result["items"]) == 2
        assert result["last_modified"] == 1234567891.00

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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "old_payload"},
                    "modified": {"N": "1234567880.00"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "old_payload"},
                    "modified": {"N": str(mock_timestamp)},
                    "sortindex": {"N": "200"},
                },
            },
        )

        updated_obj = storage_manager.update_storage_object("bookmarks", "obj123", sortindex=200)

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
                    "PK": {"S": "COLLECTION#bookmarks"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                },
            },
        )

        # Stub put_item - keep sortindex, keep ttl
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "updated_payload"},
                    "modified": {"N": str(mock_timestamp)},
                    "sortindex": {"N": "100"},
                    "ttl": {"N": "3600"},
                },
            },
        )

        updated_obj = storage_manager.update_storage_object(
            "bookmarks", "obj123", payload="updated_payload"
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
                    "PK": {"S": "COLLECTION#bookmarks"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
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
                    "PK": {"S": "COLLECTION#bookmarks"},
                    "SK": {"S": "OBJECT#obj123"},
                    "id": {"S": "obj123"},
                    "payload": {"S": "old_payload"},
                    "modified": {"N": str(mock_timestamp)},
                    "sortindex": {"N": "100"},
                },
            },
        )

        updated_obj = storage_manager.update_storage_object("bookmarks", "obj123")

        assert updated_obj.sortindex == 100
        assert updated_obj.ttl is None
