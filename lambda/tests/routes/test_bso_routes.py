"""Tests for BSO route handlers"""

import json
from unittest.mock import MagicMock

from src.routes.bso.delete import DeleteBSORoute
from src.routes.bso.read import ReadBSORoute
from src.routes.bso.update import UpdateBSORoute
from src.shared.exceptions import (
    CollectionNotFoundException,
    PreconditionFailedException,
    StorageObjectNotFoundException,
    ValidationException,
)
from src.shared.models import BasicStorageObject


class TestReadBSORoute:
    """Tests for ReadBSORoute"""

    def test_bind_registers_route(self):
        """Test that bind registers the GET route"""
        mock_storage_manager = MagicMock()
        route = ReadBSORoute(mock_storage_manager)
        mock_api = MagicMock()

        route.bind(mock_api)

        # Verify the route was registered with correct decorator chain
        mock_api.get.assert_called_once_with("/storage/{collectionName}/{objectId}")

    def test_handle_success(self, mock_storage_manager):
        """Test successful BSO retrieval"""
        route = ReadBSORoute(mock_storage_manager)

        event = {"pathParameters": {"collectionName": "bookmarks", "objectId": "item123"}}

        bso = BasicStorageObject(
            id="item123",
            payload="bookmark_data",
            modified=1234567890.12,
            sortindex=100,
            ttl=3600,
        )
        mock_storage_manager.get_storage_object.return_value = bso

        response = route.handle(event)

        mock_storage_manager.get_storage_object.assert_called_once_with("bookmarks", "item123")
        assert response.status_code == 200

        body = json.loads(response.body)
        assert body["object"]["id"] == "item123"
        assert body["object"]["payload"] == "bookmark_data"
        assert body["object"]["modified"] == 1234567890.12
        assert body["object"]["sortindex"] == 100
        assert body["object"]["ttl"] == 3600
        assert response.headers["X-Last-Modified"] == "1234567890.12"

    def test_handle_success_without_optional_fields(self, mock_storage_manager):
        """Test BSO retrieval when sortindex and ttl are None"""
        route = ReadBSORoute(mock_storage_manager)

        event = {"pathParameters": {"collectionName": "history", "objectId": "obj456"}}

        bso = BasicStorageObject(
            id="obj456",
            payload="history_data",
            modified=1234567890.12,
            sortindex=None,
            ttl=None,
        )
        mock_storage_manager.get_storage_object.return_value = bso

        response = route.handle(event)

        assert response.status_code == 200
        body = json.loads(response.body)
        assert "sortindex" not in body["object"]
        assert "ttl" not in body["object"]

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = ReadBSORoute(mock_storage_manager)

        event = {"pathParameters": {"collectionName": "invalid!@#", "objectId": "item"}}

        mock_storage_manager.get_storage_object.side_effect = ValidationException(
            "Invalid collection name"
        )

        response = route.handle(event)

        assert response.status_code == 400
        body = json.loads(response.body)
        assert "error" in body

    def test_handle_collection_not_found(self, mock_storage_manager):
        """Test handling of CollectionNotFoundException"""
        route = ReadBSORoute(mock_storage_manager)

        event = {"pathParameters": {"collectionName": "nonexistent", "objectId": "item"}}

        mock_storage_manager.get_storage_object.side_effect = CollectionNotFoundException(
            "Collection not found"
        )

        response = route.handle(event)

        assert response.status_code == 404
        body = json.loads(response.body)
        assert "error" in body

    def test_handle_storage_object_not_found(self, mock_storage_manager):
        """Test handling of StorageObjectNotFoundException"""
        route = ReadBSORoute(mock_storage_manager)

        event = {"pathParameters": {"collectionName": "bookmarks", "objectId": "nonexistent"}}

        mock_storage_manager.get_storage_object.side_effect = StorageObjectNotFoundException(
            "Object not found"
        )

        response = route.handle(event)

        assert response.status_code == 404
        body = json.loads(response.body)
        assert "error" in body

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = ReadBSORoute(mock_storage_manager)

        event = {"pathParameters": {"collectionName": "bookmarks", "objectId": "item"}}

        mock_storage_manager.get_storage_object.side_effect = Exception("Database error")

        response = route.handle(event)

        assert response.status_code == 500
        body = json.loads(response.body)
        assert body["error"] == "Internal server error"


class TestUpdateBSORoute:
    """Tests for UpdateBSORoute"""

    def test_bind_registers_route(self):
        """Test that bind registers the PUT route"""
        mock_storage_manager = MagicMock()
        route = UpdateBSORoute(mock_storage_manager)
        mock_api = MagicMock()

        route.bind(mock_api)

        mock_api.put.assert_called_once_with("/storage/{collectionName}/{objectId}")

    def test_handle_success(self, mock_storage_manager):
        """Test successful BSO update"""
        route = UpdateBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "bookmarks", "objectId": "item123"},
            "body": json.dumps(
                {
                    "object": {
                        "id": "item123",
                        "payload": "updated_data",
                        "sortindex": 200,
                        "ttl": 7200,
                    }
                }
            ),
            "headers": {},
        }

        updated_bso = BasicStorageObject(
            id="item123",
            payload="updated_data",
            modified=1234567891.00,
            sortindex=200,
            ttl=7200,
        )
        mock_storage_manager.update_storage_object.return_value = updated_bso

        response = route.handle(event)

        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["object"]["id"] == "item123"
        assert body["object"]["payload"] == "updated_data"

    def test_handle_invalid_json(self, mock_storage_manager):
        """Test handling of invalid JSON body"""
        route = UpdateBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "bookmarks", "objectId": "item"},
            "body": "invalid json{",
            "headers": {},
        }

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_missing_object_key(self, mock_storage_manager):
        """Test handling of missing 'object' key in body"""
        route = UpdateBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "bookmarks", "objectId": "item"},
            "body": json.dumps({"payload": "data"}),
            "headers": {},
        }

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_object_id_mismatch(self, mock_storage_manager):
        """Test validation when object ID doesn't match path"""
        route = UpdateBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "bookmarks", "objectId": "item123"},
            "body": json.dumps({"object": {"id": "different_id", "payload": "data"}}),
            "headers": {},
        }

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_with_precondition_header(self, mock_storage_manager):
        """Test with X-If-Unmodified-Since header"""
        route = UpdateBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "bookmarks", "objectId": "item123"},
            "body": json.dumps({"object": {"id": "item123", "payload": "data"}}),
            "headers": {"X-If-Unmodified-Since": "1234567890"},
        }

        updated_bso = BasicStorageObject(
            id="item123",
            payload="data",
            modified=1234567891.00,
            sortindex=None,
            ttl=None,
        )
        mock_storage_manager.update_storage_object.return_value = updated_bso

        response = route.handle(event)

        assert response.status_code == 200

    def test_handle_invalid_precondition_header(self, mock_storage_manager):
        """Test with invalid X-If-Unmodified-Since header"""
        route = UpdateBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "bookmarks", "objectId": "item123"},
            "body": json.dumps({"object": {"id": "item123", "payload": "data"}}),
            "headers": {"X-If-Unmodified-Since": "invalid"},
        }

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_collection_not_found(self, mock_storage_manager):
        """Test handling of CollectionNotFoundException"""
        route = UpdateBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "nonexistent", "objectId": "item123"},
            "body": json.dumps({"object": {"id": "item123", "payload": "data"}}),
            "headers": {},
        }

        mock_storage_manager.update_storage_object.side_effect = CollectionNotFoundException(
            "Not found"
        )

        response = route.handle(event)

        assert response.status_code == 404

    def test_handle_object_not_found(self, mock_storage_manager):
        """Test handling of StorageObjectNotFoundException"""
        route = UpdateBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {
                "collectionName": "bookmarks",
                "objectId": "nonexistent",
            },
            "body": json.dumps({"object": {"id": "nonexistent", "payload": "data"}}),
            "headers": {},
        }

        mock_storage_manager.update_storage_object.side_effect = StorageObjectNotFoundException(
            "Not found"
        )

        response = route.handle(event)

        assert response.status_code == 404

    def test_handle_precondition_failed(self, mock_storage_manager):
        """Test handling of PreconditionFailedException"""
        route = UpdateBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "bookmarks", "objectId": "item123"},
            "body": json.dumps({"object": {"id": "item123", "payload": "data"}}),
            "headers": {},
        }

        mock_storage_manager.update_storage_object.side_effect = PreconditionFailedException(
            "Failed"
        )

        response = route.handle(event)

        assert response.status_code == 412

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = UpdateBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "invalid!", "objectId": "item123"},
            "body": json.dumps({"object": {"id": "item123", "payload": "data"}}),
            "headers": {},
        }

        mock_storage_manager.update_storage_object.side_effect = ValidationException("Invalid")

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = UpdateBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "bookmarks", "objectId": "item"},
            "body": json.dumps({"object": {"id": "item", "payload": "data"}}),
            "headers": {},
        }

        mock_storage_manager.update_storage_object.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500


class TestDeleteBSORoute:
    """Tests for DeleteBSORoute"""

    def test_bind_registers_route(self):
        """Test that bind registers the DELETE route"""
        mock_storage_manager = MagicMock()
        route = DeleteBSORoute(mock_storage_manager)
        mock_api = MagicMock()

        route.bind(mock_api)

        mock_api.delete.assert_called_once_with("/storage/{collectionName}/{objectId}")

    def test_handle_success(self, mock_storage_manager):
        """Test successful BSO deletion"""
        route = DeleteBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "bookmarks", "objectId": "item123"},
            "headers": {},
        }

        mock_storage_manager.delete_storage_object.return_value = 1234567892.00

        response = route.handle(event)

        mock_storage_manager.delete_storage_object.assert_called_once_with("bookmarks", "item123")
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["modified"] == 1234567892.00

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = DeleteBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "invalid!", "objectId": "item"},
            "headers": {},
        }

        mock_storage_manager.delete_storage_object.side_effect = ValidationException("Invalid")

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_collection_not_found(self, mock_storage_manager):
        """Test handling of CollectionNotFoundException"""
        route = DeleteBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "nonexistent", "objectId": "item"},
            "headers": {},
        }

        mock_storage_manager.delete_storage_object.side_effect = CollectionNotFoundException(
            "Not found"
        )

        response = route.handle(event)

        assert response.status_code == 404

    def test_handle_object_not_found(self, mock_storage_manager):
        """Test handling of StorageObjectNotFoundException"""
        route = DeleteBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {
                "collectionName": "bookmarks",
                "objectId": "nonexistent",
            },
            "headers": {},
        }

        mock_storage_manager.delete_storage_object.side_effect = StorageObjectNotFoundException(
            "Not found"
        )

        response = route.handle(event)

        assert response.status_code == 404

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = DeleteBSORoute(mock_storage_manager)

        event = {
            "pathParameters": {"collectionName": "bookmarks", "objectId": "item"},
            "headers": {},
        }

        mock_storage_manager.delete_storage_object.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500
