from datetime import datetime, timezone

"""Tests for collection route handlers"""

import json
from typing import Any
from unittest.mock import MagicMock

from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.collections.create import CreateCollectionRoute
from src.routes.collections.delete import DeleteCollectionRoute
from src.routes.collections.list import ListCollectionsRoute
from src.routes.collections.read import ReadCollectionRoute
from src.routes.collections.update import UpdateCollectionRoute
from src.shared.exceptions import (
    CollectionNotFoundException,
    ConflictException,
    PreconditionFailedException,
    ValidationException,
)
from src.shared.models import BasicStorageObject, BatchResult, CollectionData


class TestCreateCollectionRoute:
    """Tests for CreateCollectionRoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the POST route and handler works through resolver"""
        route = CreateCollectionRoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event: dict[str, Any] = {
            "httpMethod": "POST",
            "path": "/storage/bookmarks",
            "pathParameters": {"collectionName": "bookmarks"},
            "headers": {},
            "body": None,
            "requestContext": {},
        }
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 201

    def test_handle_success_with_objects(self, mock_storage_manager):
        """Test successful collection creation with objects"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "headers": {},
                "body": json.dumps(
                    {
                        "objects": [
                            {"id": "obj1", "payload": "data1", "sortindex": 100},
                            {"id": "obj2", "payload": "data2"},
                        ]
                    }
                ),
            }
        )

        collection_data = CollectionData(
            name="bookmarks",
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            count=2,
            usage=1024,
        )
        batch_result = BatchResult(
            success=["obj1", "obj2"],
            failed={},
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
        )
        mock_storage_manager.create_or_update_collection.return_value = (
            collection_data,
            batch_result,
        )

        response = route.handle(event)

        assert response.status_code == 201
        assert response.body is not None
        body = json.loads(response.body)
        assert body["collection"]["name"] == "bookmarks"
        assert body["batchResult"]["success"] == ["obj1", "obj2"]

    def test_handle_success_with_array_format(self, mock_storage_manager):
        """Test collection creation with direct array format"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "tabs"},
                "headers": {},
                "body": json.dumps(
                    [{"id": "tab1", "payload": "data1"}, {"id": "tab2", "payload": "data2"}]
                ),
            }
        )

        collection_data = CollectionData(
            name="tabs",
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            count=2,
            usage=512,
        )
        batch_result = BatchResult(
            success=["tab1", "tab2"],
            failed={},
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
        )
        mock_storage_manager.create_or_update_collection.return_value = (
            collection_data,
            batch_result,
        )

        response = route.handle(event)

        assert response.status_code == 201

    def test_handle_success_without_objects(self, mock_storage_manager):
        """Test collection creation without objects"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "history"},
                "headers": {},
                "body": None,
            }
        )

        collection_data = CollectionData(
            name="history",
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            count=0,
            usage=0,
        )
        batch_result = BatchResult(
            success=[], failed={}, modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc)
        )
        mock_storage_manager.create_or_update_collection.return_value = (
            collection_data,
            batch_result,
        )

        response = route.handle(event)

        assert response.status_code == 201

    def test_handle_with_precondition_header(self, mock_storage_manager):
        """Test handling of X-If-Unmodified-Since header"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "headers": {"X-If-Unmodified-Since": "1234567889.00"},
                "body": json.dumps({"objects": []}),
            }
        )

        # Collection was modified after the timestamp
        existing_collection = CollectionData(
            name="bookmarks",
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            count=1,
            usage=100,
        )
        mock_storage_manager.get_collection.return_value = existing_collection

        response = route.handle(event)

        assert response.status_code == 412

    def test_handle_precondition_check_passes(self, mock_storage_manager):
        """Test precondition check when collection hasn't been modified"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "headers": {"X-If-Unmodified-Since": "1234567891.00"},
                "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
            }
        )

        existing_collection = CollectionData(
            name="bookmarks",
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            count=0,
            usage=0,
        )
        mock_storage_manager.get_collection.return_value = existing_collection

        collection_data = CollectionData(
            name="bookmarks",
            modified=datetime.fromtimestamp(1234567891.00, tz=timezone.utc),
            count=1,
            usage=100,
        )
        batch_result = BatchResult(
            success=["obj1"],
            failed={},
            modified=datetime.fromtimestamp(1234567891.00, tz=timezone.utc),
        )
        mock_storage_manager.create_or_update_collection.return_value = (
            collection_data,
            batch_result,
        )

        response = route.handle(event)

        assert response.status_code == 201

    def test_handle_invalid_json(self, mock_storage_manager):
        """Test handling of invalid JSON in body"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "headers": {},
                "body": "invalid json{",
            }
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "invalid!"},
                "headers": {},
                "body": None,
            }
        )

        mock_storage_manager.create_or_update_collection.side_effect = ValidationException(
            "Invalid name"
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_conflict_exception(self, mock_storage_manager):
        """Test handling of ConflictException"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "headers": {},
                "body": None,
            }
        )

        mock_storage_manager.create_or_update_collection.side_effect = ConflictException("Conflict")

        response = route.handle(event)

        assert response.status_code == 409

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "headers": {},
                "body": None,
            }
        )

        mock_storage_manager.create_or_update_collection.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500


class TestReadCollectionRoute:
    """Tests for ReadCollectionRoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the GET route and handler works through resolver"""
        route = ReadCollectionRoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event = {
            "httpMethod": "GET",
            "path": "/storage/bookmarks",
            "pathParameters": {"collectionName": "bookmarks"},
            "queryStringParameters": None,
            "headers": {},
            "body": None,
            "requestContext": {},
        }
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_metadata_only(self, mock_storage_manager):
        """Test getting collection metadata without objects"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "queryStringParameters": None,
            }
        )

        collection_data = CollectionData(
            name="bookmarks",
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            count=5,
            usage=2048,
        )
        mock_storage_manager.get_collection.return_value = collection_data

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body["collection"]["name"] == "bookmarks"
        assert body["collection"]["count"] == 5

    def test_handle_with_object_filters(self, mock_storage_manager):
        """Test getting collection objects with filters"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "queryStringParameters": {
                    "newer": "1234567880.00",
                    "limit": "10",
                    "sort": "newest",
                },
            }
        )

        objects = {
            "items": [
                BasicStorageObject(
                    id="obj1",
                    payload="data1",
                    modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
                    sortindex=100,
                    ttl=3600,
                )
            ],
            "more": False,
            "last_modified": 1234567890.12,
        }
        mock_storage_manager.get_collection_objects.return_value = objects

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert len(body["objects"]) == 1
        assert body["more"] is False

    def test_handle_objects_with_pagination(self, mock_storage_manager):
        """Test getting objects with pagination"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "history"},
                "queryStringParameters": {"limit": "5", "offset": "10"},
            }
        )

        objects = {
            "items": [
                BasicStorageObject(
                    id=f"obj{i}",
                    payload=f"data{i}",
                    modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
                    sortindex=None,
                    ttl=None,
                )
                for i in range(5)
            ],
            "more": True,
            "next_offset": 15,
            "last_modified": 1234567890.12,
        }
        mock_storage_manager.get_collection_objects.return_value = objects

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body["more"] is True
        assert body["next_offset"] == 15

    def test_handle_objects_without_optional_fields(self, mock_storage_manager):
        """Test formatting objects without sortindex/ttl"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "tabs"},
                "queryStringParameters": {"ids": "obj1,obj2"},
            }
        )

        objects = {
            "items": [
                BasicStorageObject(
                    id="obj1",
                    payload="data1",
                    modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
                    sortindex=None,
                    ttl=None,
                )
            ],
            "more": False,
            "last_modified": 1234567890.12,
        }
        mock_storage_manager.get_collection_objects.return_value = objects

        response = route.handle(event)

        assert response.body is not None
        body = json.loads(response.body)
        assert "sortindex" not in body["objects"][0]
        assert "ttl" not in body["objects"][0]

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "invalid!"},
                "queryStringParameters": None,
            }
        )

        mock_storage_manager.get_collection.side_effect = ValidationException("Invalid")

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_collection_not_found(self, mock_storage_manager):
        """Test handling of CollectionNotFoundException"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "nonexistent"},
                "queryStringParameters": None,
            }
        )

        mock_storage_manager.get_collection.side_effect = CollectionNotFoundException("Not found")

        response = route.handle(event)

        assert response.status_code == 404

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "queryStringParameters": None,
            }
        )

        mock_storage_manager.get_collection.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500


class TestUpdateCollectionRoute:
    """Tests for UpdateCollectionRoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the PUT route and handler works through resolver"""
        collection_data = CollectionData(
            name="bookmarks",
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            count=1,
            usage=100,
        )
        batch_result = BatchResult(
            success=["obj1"],
            failed={},
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
        )
        mock_storage_manager.update_collection.return_value = (collection_data, batch_result)

        route = UpdateCollectionRoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event = {
            "httpMethod": "PUT",
            "path": "/storage/bookmarks",
            "pathParameters": {"collectionName": "bookmarks"},
            "headers": {},
            "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
            "requestContext": {},
        }
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self, mock_storage_manager):
        """Test successful collection update"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "headers": {},
                "body": json.dumps({"objects": [{"id": "obj1", "payload": "updated"}]}),
            }
        )

        collection_data = CollectionData(
            name="bookmarks",
            modified=datetime.fromtimestamp(1234567891.00, tz=timezone.utc),
            count=1,
            usage=512,
        )
        batch_result = BatchResult(
            success=["obj1"],
            failed={},
            modified=datetime.fromtimestamp(1234567891.00, tz=timezone.utc),
        )
        mock_storage_manager.update_collection.return_value = (
            collection_data,
            batch_result,
        )

        response = route.handle(event)

        assert response.status_code == 200

    def test_handle_invalid_json(self, mock_storage_manager):
        """Test handling of invalid JSON in body"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "headers": {},
                "body": "invalid json{",
            }
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_missing_objects_key(self, mock_storage_manager):
        """Test handling of missing 'objects' key in body"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "headers": {},
                "body": json.dumps({"data": []}),
            }
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_with_precondition_header(self, mock_storage_manager):
        """Test with X-If-Unmodified-Since header"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "headers": {"X-If-Unmodified-Since": "1234567890"},
                "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
            }
        )

        collection_data = CollectionData(
            name="bookmarks",
            modified=datetime.fromtimestamp(1234567891.00, tz=timezone.utc),
            count=1,
            usage=512,
        )
        batch_result = BatchResult(
            success=["obj1"],
            failed={},
            modified=datetime.fromtimestamp(1234567891.00, tz=timezone.utc),
        )
        mock_storage_manager.update_collection.return_value = (
            collection_data,
            batch_result,
        )

        response = route.handle(event)

        assert response.status_code == 200

    def test_handle_invalid_precondition_header(self, mock_storage_manager):
        """Test with invalid X-If-Unmodified-Since header"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "headers": {"X-If-Unmodified-Since": "invalid"},
                "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
            }
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "invalid!"},
                "headers": {},
                "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
            }
        )

        mock_storage_manager.update_collection.side_effect = ValidationException("Invalid")

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_collection_not_found(self, mock_storage_manager):
        """Test handling of CollectionNotFoundException"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "nonexistent"},
                "headers": {},
                "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
            }
        )

        mock_storage_manager.update_collection.side_effect = CollectionNotFoundException(
            "Not found"
        )

        response = route.handle(event)

        assert response.status_code == 404

    def test_handle_precondition_failed(self, mock_storage_manager):
        """Test handling of PreconditionFailedException"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "headers": {},
                "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
            }
        )

        mock_storage_manager.update_collection.side_effect = PreconditionFailedException("Failed")

        response = route.handle(event)

        assert response.status_code == 412

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"collectionName": "bookmarks"},
                "headers": {},
                "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
            }
        )

        mock_storage_manager.update_collection.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500


class TestDeleteCollectionRoute:
    """Tests for DeleteCollectionRoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the DELETE route and handler works through resolver"""
        mock_storage_manager.delete_collection.return_value = 1234567890.12
        route = DeleteCollectionRoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event = {
            "httpMethod": "DELETE",
            "path": "/storage/bookmarks",
            "pathParameters": {"collectionName": "bookmarks"},
            "headers": {},
            "body": None,
            "requestContext": {},
        }
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self, mock_storage_manager):
        """Test successful collection deletion"""
        route = DeleteCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent({"pathParameters": {"collectionName": "bookmarks"}})

        mock_storage_manager.delete_collection.return_value = 1234567892.00

        response = route.handle(event)

        mock_storage_manager.delete_collection.assert_called_once_with("bookmarks")
        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body["modified"] == 1234567892.00

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = DeleteCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent({"pathParameters": {"collectionName": "invalid!"}})

        mock_storage_manager.delete_collection.side_effect = ValidationException("Invalid")

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_collection_not_found(self, mock_storage_manager):
        """Test handling of CollectionNotFoundException"""
        route = DeleteCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent({"pathParameters": {"collectionName": "nonexistent"}})

        mock_storage_manager.delete_collection.side_effect = CollectionNotFoundException(
            "Not found"
        )

        response = route.handle(event)

        assert response.status_code == 404

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = DeleteCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent({"pathParameters": {"collectionName": "bookmarks"}})

        mock_storage_manager.delete_collection.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500


class TestListCollectionsRoute:
    """Tests for ListCollectionsRoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the GET route and handler works through resolver"""
        mock_storage_manager.list_collections.return_value = []
        route = ListCollectionsRoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event: dict[str, Any] = {
            "httpMethod": "GET",
            "path": "/storage",
            "pathParameters": None,
            "queryStringParameters": None,
            "headers": {},
            "body": None,
            "requestContext": {},
        }
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self, mock_storage_manager):
        """Test successful collection listing"""
        route = ListCollectionsRoute(mock_storage_manager)

        event = APIGatewayProxyEvent({"queryStringParameters": None})

        collections = [
            CollectionData(
                name="bookmarks",
                modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
                count=5,
                usage=1024,
            ),
            CollectionData(
                name="history",
                modified=datetime.fromtimestamp(1234567880.00, tz=timezone.utc),
                count=10,
                usage=2048,
            ),
        ]
        mock_storage_manager.list_collections.return_value = collections

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert len(body["collections"]) == 2
        assert body["collections"][0]["name"] == "bookmarks"

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = ListCollectionsRoute(mock_storage_manager)

        event = APIGatewayProxyEvent({"queryStringParameters": None})

        mock_storage_manager.list_collections.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500
