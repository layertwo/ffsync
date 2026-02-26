"""Tests for BSO route handlers"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

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

TEST_USER_ID = "test-user-123"


def with_auth(event_dict: dict) -> dict:
    """Add authorizer context to event dict"""
    if "requestContext" not in event_dict:
        event_dict["requestContext"] = {}
    event_dict["requestContext"]["authorizer"] = {"user_id": TEST_USER_ID}
    return event_dict


class TestReadBSORoute:
    """Tests for ReadBSORoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the GET route and handler works through resolver"""
        route = ReadBSORoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        # Test through the resolver
        event = {
            "httpMethod": "GET",
            "path": "/1.5/12345/storage/bookmarks/item123",
            "pathParameters": {
                "uid": "12345",
                "collectionName": "bookmarks",
                "objectId": "item123",
            },
            "headers": {},
            "body": None,
            "requestContext": {"authorizer": {"user_id": "test-user-123"}},
        }
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self, mock_storage_manager):
        """Test successful BSO retrieval"""
        route = ReadBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        bso = BasicStorageObject(
            id="item123",
            payload="bookmark_data",
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            sortindex=100,
            ttl=3600,
        )
        mock_storage_manager.get_storage_object.return_value = bso

        response = route.handle(event)

        mock_storage_manager.get_storage_object.assert_called_once_with(
            "test-user-123", "bookmarks", "item123"
        )
        assert response.status_code == 200

        assert response.body is not None
        body = json.loads(response.body)
        assert body["id"] == "item123"
        assert body["payload"] == "bookmark_data"
        assert body["modified"] == 1234567890.12
        assert body["sortindex"] == 100
        # TTL is write-only per Mozilla spec (Requirement 11.4) - should not be in response
        assert "ttl" not in body
        assert response.headers["X-Last-Modified"] == "1234567890.12"

    def test_handle_success_without_optional_fields(self, mock_storage_manager):
        """Test BSO retrieval when sortindex and ttl are None"""
        route = ReadBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "history",
                    "objectId": "obj456",
                },
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        bso = BasicStorageObject(
            id="obj456",
            payload="history_data",
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            sortindex=None,
            ttl=None,
        )
        mock_storage_manager.get_storage_object.return_value = bso

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert "sortindex" not in body
        assert "ttl" not in body

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = ReadBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "invalid!@#",
                    "objectId": "item",
                },
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.get_storage_object.side_effect = ValidationException(
            "Invalid collection name"
        )

        response = route.handle(event)

        assert response.status_code == 400
        assert response.body is not None
        body = json.loads(response.body)
        assert "error" in body

    def test_handle_collection_not_found(self, mock_storage_manager):
        """Test handling of CollectionNotFoundException"""
        route = ReadBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "nonexistent",
                    "objectId": "item",
                },
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.get_storage_object.side_effect = CollectionNotFoundException(
            "Collection not found"
        )

        response = route.handle(event)

        assert response.status_code == 404
        assert response.body is not None
        body = json.loads(response.body)
        assert "error" in body

    def test_handle_storage_object_not_found(self, mock_storage_manager):
        """Test handling of StorageObjectNotFoundException"""
        route = ReadBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "nonexistent",
                },
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.get_storage_object.side_effect = StorageObjectNotFoundException(
            "Object not found"
        )

        response = route.handle(event)

        assert response.status_code == 404
        assert response.body is not None
        body = json.loads(response.body)
        assert "error" in body

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = ReadBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item",
                },
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.get_storage_object.side_effect = Exception("Database error")

        response = route.handle(event)

        assert response.status_code == 500
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Internal server error"


class TestUpdateBSORoute:
    """Tests for UpdateBSORoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the PUT route and handler works through resolver"""
        updated_bso = BasicStorageObject(
            id="item123",
            payload="data",
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            sortindex=None,
            ttl=None,
        )
        mock_storage_manager.update_storage_object.return_value = updated_bso

        route = UpdateBSORoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event = {
            "httpMethod": "PUT",
            "path": "/1.5/12345/storage/bookmarks/item123",
            "pathParameters": {
                "uid": "12345",
                "collectionName": "bookmarks",
                "objectId": "item123",
            },
            "headers": {},
            "body": json.dumps({"id": "item123", "payload": "data"}),
            "requestContext": {"authorizer": {"user_id": "test-user-123"}},
        }
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self, mock_storage_manager):
        """Test successful BSO update"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "body": json.dumps(
                    {
                        "id": "item123",
                        "payload": "updated_data",
                        "sortindex": 200,
                        "ttl": 7200,
                    }
                ),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        updated_bso = BasicStorageObject(
            id="item123",
            payload="updated_data",
            modified=datetime.fromtimestamp(1234567891.00, tz=timezone.utc),
            sortindex=200,
            ttl=7200,
        )
        mock_storage_manager.update_storage_object.return_value = updated_bso

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body == 1234567891.0

    def test_handle_invalid_json(self, mock_storage_manager):
        """Test handling of invalid JSON body"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item",
                },
                "body": "invalid json{",
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_non_object_body(self, mock_storage_manager):
        """Test handling of non-object JSON body (e.g. array or string)"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item",
                },
                "body": json.dumps([1, 2, 3]),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_object_id_mismatch(self, mock_storage_manager):
        """Test validation when object ID doesn't match path"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "body": json.dumps({"id": "different_id", "payload": "data"}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_with_precondition_header(self, mock_storage_manager):
        """Test with X-If-Unmodified-Since header"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "body": json.dumps({"id": "item123", "payload": "data"}),
                "headers": {"X-If-Unmodified-Since": "1234567890"},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        updated_bso = BasicStorageObject(
            id="item123",
            payload="data",
            modified=datetime.fromtimestamp(1234567891.00, tz=timezone.utc),
            sortindex=None,
            ttl=None,
        )
        mock_storage_manager.update_storage_object.return_value = updated_bso

        response = route.handle(event)

        assert response.status_code == 200

    def test_handle_invalid_precondition_header(self, mock_storage_manager):
        """Test with invalid X-If-Unmodified-Since header"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "body": json.dumps({"id": "item123", "payload": "data"}),
                "headers": {"X-If-Unmodified-Since": "invalid"},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_collection_not_found(self, mock_storage_manager):
        """Test handling of CollectionNotFoundException"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "nonexistent",
                    "objectId": "item123",
                },
                "body": json.dumps({"id": "item123", "payload": "data"}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.update_storage_object.side_effect = CollectionNotFoundException(
            "Not found"
        )

        response = route.handle(event)

        assert response.status_code == 404

    def test_handle_object_not_found(self, mock_storage_manager):
        """Test handling of StorageObjectNotFoundException"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "nonexistent",
                },
                "body": json.dumps({"id": "nonexistent", "payload": "data"}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.update_storage_object.side_effect = StorageObjectNotFoundException(
            "Not found"
        )

        response = route.handle(event)

        assert response.status_code == 404

    def test_handle_precondition_failed(self, mock_storage_manager):
        """Test handling of PreconditionFailedException"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "body": json.dumps({"id": "item123", "payload": "data"}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.update_storage_object.side_effect = PreconditionFailedException(
            "Failed"
        )

        response = route.handle(event)

        assert response.status_code == 412

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "invalid!",
                    "objectId": "item123",
                },
                "body": json.dumps({"id": "item123", "payload": "data"}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.update_storage_object.side_effect = ValidationException("Invalid")

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item",
                },
                "body": json.dumps({"id": "item", "payload": "data"}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.update_storage_object.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500


class TestDeleteBSORoute:
    """Tests for DeleteBSORoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the DELETE route and handler works through resolver"""
        mock_storage_manager.delete_storage_object.return_value = 1234567890.12
        route = DeleteBSORoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event = {
            "httpMethod": "DELETE",
            "path": "/1.5/12345/storage/bookmarks/item123",
            "pathParameters": {
                "uid": "12345",
                "collectionName": "bookmarks",
                "objectId": "item123",
            },
            "headers": {},
            "body": None,
            "requestContext": {"authorizer": {"user_id": "test-user-123"}},
        }
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self, mock_storage_manager):
        """Test successful BSO deletion"""
        route = DeleteBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.delete_storage_object.return_value = 1234567892.00

        response = route.handle(event)

        mock_storage_manager.delete_storage_object.assert_called_once_with(
            "test-user-123", "bookmarks", "item123"
        )
        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body["modified"] == 1234567892.00

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = DeleteBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "invalid!",
                    "objectId": "item",
                },
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.delete_storage_object.side_effect = ValidationException("Invalid")

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_collection_not_found(self, mock_storage_manager):
        """Test handling of CollectionNotFoundException"""
        route = DeleteBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "nonexistent",
                    "objectId": "item",
                },
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.delete_storage_object.side_effect = CollectionNotFoundException(
            "Not found"
        )

        response = route.handle(event)

        assert response.status_code == 404

    def test_handle_object_not_found(self, mock_storage_manager):
        """Test handling of StorageObjectNotFoundException"""
        route = DeleteBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "nonexistent",
                },
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.delete_storage_object.side_effect = StorageObjectNotFoundException(
            "Not found"
        )

        response = route.handle(event)

        assert response.status_code == 404

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = DeleteBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item",
                },
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        mock_storage_manager.delete_storage_object.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500


class TestReadBSORouteUnauthorized:
    """Tests for ReadBSORoute unauthorized cases"""

    def test_handle_unauthorized_missing_user_id(self, mock_storage_manager):
        """Test handling when user_id is missing from authorizer context"""
        route = ReadBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "headers": {},
                "requestContext": {"authorizer": {}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 401
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Unauthorized"


class TestDeleteBSORouteUnauthorized:
    """Tests for DeleteBSORoute unauthorized cases"""

    def test_handle_unauthorized_missing_user_id(self, mock_storage_manager):
        """Test handling when user_id is missing from authorizer context"""
        route = DeleteBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "requestContext": {"authorizer": {}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 401
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Unauthorized"


class TestUpdateBSORouteUnauthorized:
    """Tests for UpdateBSORoute unauthorized cases"""

    def test_handle_unauthorized_missing_user_id(self, mock_storage_manager):
        """Test handling when user_id is missing from authorizer context"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "body": json.dumps({"id": "item123", "payload": "data"}),
                "headers": {},
                "requestContext": {"authorizer": {}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 401
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Unauthorized"


class TestReadBSORouteConditionalGET:
    """Tests for ReadBSORoute conditional GET support (Requirements 6.1-6.4)"""

    def test_handle_if_modified_since_not_modified(self, mock_storage_manager):
        """Test 304 Not Modified when resource hasn't changed"""
        route = ReadBSORoute(mock_storage_manager)

        bso = BasicStorageObject(
            id="item123",
            payload="data",
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            sortindex=None,
            ttl=None,
        )
        mock_storage_manager.get_storage_object.return_value = bso

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "headers": {"x-if-modified-since": "1234567890.12"},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 304
        assert response.headers["X-Last-Modified"] == "1234567890.12"

    def test_handle_if_modified_since_modified(self, mock_storage_manager):
        """Test 200 OK when resource has been modified"""
        route = ReadBSORoute(mock_storage_manager)

        bso = BasicStorageObject(
            id="item123",
            payload="data",
            modified=datetime.fromtimestamp(1234567900.00, tz=timezone.utc),
            sortindex=None,
            ttl=None,
        )
        mock_storage_manager.get_storage_object.return_value = bso

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "headers": {"x-if-modified-since": "1234567890.12"},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body["id"] == "item123"

    def test_handle_if_modified_since_invalid_format(self, mock_storage_manager):
        """Test 400 Bad Request for invalid X-If-Modified-Since header"""
        route = ReadBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "headers": {"x-if-modified-since": "invalid"},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400
        assert response.body is not None
        body = json.loads(response.body)
        assert "Invalid X-If-Modified-Since header" in body["error"]

    def test_handle_if_modified_since_negative(self, mock_storage_manager):
        """Test 400 Bad Request for negative X-If-Modified-Since value"""
        route = ReadBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "headers": {"x-if-modified-since": "-123.45"},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400
        assert response.body is not None
        body = json.loads(response.body)
        assert "Invalid X-If-Modified-Since header" in body["error"]

    def test_handle_both_conditional_headers(self, mock_storage_manager):
        """Test 400 Bad Request when both X-If-Modified-Since and X-If-Unmodified-Since are present"""
        route = ReadBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "headers": {
                    "x-if-modified-since": "1234567890.12",
                    "x-if-unmodified-since": "1234567890.12",
                },
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400
        assert response.body is not None
        body = json.loads(response.body)
        assert "Cannot specify both" in body["error"]


class TestReadBSORouteInvalidInputs:
    """Tests that validate_collection_name and validate_bso_id are called in ReadBSORoute"""

    def test_handle_invalid_collection_name(self, mock_storage_manager):
        """Test that invalid collection name returns 400 without calling storage"""
        route = ReadBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {
                        "uid": "12345",
                        "collectionName": "invalid name!",
                        "objectId": "item123",
                    },
                    "headers": {},
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400
        mock_storage_manager.get_storage_object.assert_not_called()

    def test_handle_invalid_bso_id(self, mock_storage_manager):
        """Test that invalid BSO ID returns 400 without calling storage"""
        route = ReadBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {
                        "uid": "12345",
                        "collectionName": "bookmarks",
                        "objectId": "invalid\x01id",
                    },
                    "headers": {},
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400
        mock_storage_manager.get_storage_object.assert_not_called()


class TestUpdateBSORouteInvalidCollectionName:
    """Tests that validate_collection_name is called before body parsing in UpdateBSORoute"""

    def test_handle_invalid_collection_name(self, mock_storage_manager):
        """Test that invalid collection name returns 400 without calling storage"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {
                        "uid": "12345",
                        "collectionName": "invalid name!",
                        "objectId": "item123",
                    },
                    "body": json.dumps({"id": "item123", "payload": "data"}),
                    "headers": {},
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400
        mock_storage_manager.update_storage_object.assert_not_called()


class TestDeleteBSORouteInvalidInputs:
    """Tests that validate_collection_name and validate_bso_id are called in DeleteBSORoute"""

    def test_handle_invalid_collection_name(self, mock_storage_manager):
        """Test that invalid collection name returns 400 without calling storage"""
        route = DeleteBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {
                        "uid": "12345",
                        "collectionName": "invalid name!",
                        "objectId": "item123",
                    },
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400
        mock_storage_manager.delete_storage_object.assert_not_called()

    def test_handle_invalid_bso_id(self, mock_storage_manager):
        """Test that invalid BSO ID returns 400 without calling storage"""
        route = DeleteBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {
                        "uid": "12345",
                        "collectionName": "bookmarks",
                        "objectId": "invalid\x01id",
                    },
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400
        mock_storage_manager.delete_storage_object.assert_not_called()


class TestUpdateBSORouteValidation:
    """Tests for UpdateBSORoute validation (Requirements 10.1-10.5)"""

    def test_handle_payload_too_large(self, mock_storage_manager):
        """Test 413 Request Too Large for oversized payload"""
        route = UpdateBSORoute(mock_storage_manager)

        # Create a payload larger than 256 KB
        large_payload = "x" * (256 * 1024 + 1)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "body": json.dumps({"id": "item123", "payload": large_payload}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 413
        assert response.body is not None
        body = json.loads(response.body)
        assert "Payload size" in body["error"]

    def test_handle_bso_id_too_long(self, mock_storage_manager):
        """Test 400 Bad Request for BSO ID exceeding 64 characters"""
        route = UpdateBSORoute(mock_storage_manager)

        long_id = "x" * 65

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": long_id,
                },
                "body": json.dumps({"id": long_id, "payload": "data"}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400
        assert response.body is not None
        body = json.loads(response.body)
        assert "BSO ID length" in body["error"]

    def test_handle_bso_id_non_printable_ascii(self, mock_storage_manager):
        """Test 400 Bad Request for BSO ID with non-printable ASCII"""
        route = UpdateBSORoute(mock_storage_manager)

        invalid_id = "item\x00123"

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": invalid_id,
                },
                "body": json.dumps({"id": invalid_id, "payload": "data"}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400
        assert response.body is not None
        body = json.loads(response.body)
        assert "non-printable ASCII" in body["error"]

    def test_handle_sortindex_invalid(self, mock_storage_manager):
        """Test 400 Bad Request for invalid sortindex"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "body": json.dumps({"id": "item123", "payload": "data", "sortindex": "not_an_int"}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400
        assert response.body is not None
        body = json.loads(response.body)
        assert "Sortindex must be an integer" in body["error"]

    def test_handle_sortindex_exceeds_max(self, mock_storage_manager):
        """Test 400 Bad Request for sortindex exceeding 9 digits"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "body": json.dumps({"id": "item123", "payload": "data", "sortindex": 1000000000}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400
        assert response.body is not None
        body = json.loads(response.body)
        assert "Sortindex" in body["error"] and "exceeds" in body["error"]

    def test_handle_ttl_invalid(self, mock_storage_manager):
        """Test 400 Bad Request for invalid TTL"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "body": json.dumps({"id": "item123", "payload": "data", "ttl": "not_an_int"}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400
        assert response.body is not None
        body = json.loads(response.body)
        assert "TTL must be an integer" in body["error"]

    def test_handle_ttl_negative(self, mock_storage_manager):
        """Test 400 Bad Request for negative TTL"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "body": json.dumps({"id": "item123", "payload": "data", "ttl": -100}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400
        assert response.body is not None
        body = json.loads(response.body)
        assert "TTL must be a positive integer" in body["error"]

    def test_handle_ttl_exceeds_max(self, mock_storage_manager):
        """Test 400 Bad Request for TTL exceeding 9 digits"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "body": json.dumps({"id": "item123", "payload": "data", "ttl": 1000000000}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 400
        assert response.body is not None
        body = json.loads(response.body)
        assert "TTL" in body["error"] and "exceeds" in body["error"]

    def test_handle_no_payload(self, mock_storage_manager):
        """Test successful update without payload (partial update)"""
        route = UpdateBSORoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {
                    "uid": "12345",
                    "collectionName": "bookmarks",
                    "objectId": "item123",
                },
                "body": json.dumps({"sortindex": 50}),
                "headers": {},
                "requestContext": {"authorizer": {"user_id": "test-user-123"}},
            }
        )

        updated_bso = BasicStorageObject(
            id="item123",
            payload="existing_data",
            modified=datetime.fromtimestamp(1234567891.00, tz=timezone.utc),
            sortindex=50,
            ttl=None,
        )
        mock_storage_manager.update_storage_object.return_value = updated_bso

        response = route.handle(event)

        assert response.status_code == 200
        mock_storage_manager.update_storage_object.assert_called_once_with(
            "test-user-123",
            "bookmarks",
            "item123",
            if_unmodified_since=None,
            payload=None,
            sortindex=50,
            ttl=None,
        )
