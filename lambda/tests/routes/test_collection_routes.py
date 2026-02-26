from datetime import datetime, timezone

"""Tests for collection route handlers"""

import json
from typing import Any
from unittest.mock import ANY, MagicMock

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

TEST_USER_ID = "test-user-123"
AUTH_CONTEXT = {"requestContext": {"authorizer": {"user_id": TEST_USER_ID}}}


def with_auth(event_dict: dict) -> dict:
    """Add authorizer context to event dict"""
    event_dict["requestContext"] = {"authorizer": {"user_id": TEST_USER_ID}}
    return event_dict


class TestCreateCollectionRoute:
    """Tests for CreateCollectionRoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the POST route and handler works through resolver"""
        route = CreateCollectionRoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event: dict[str, Any] = with_auth(
            {
                "httpMethod": "POST",
                "path": "/1.5/12345/storage/bookmarks",
                "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                "headers": {},
                "body": None,
            }
        )
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 201

    def test_handle_success_with_objects(self, mock_storage_manager):
        """Test successful collection creation with objects"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
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
        # Mozilla-compliant response format
        assert body["modified"] == 1234567890.12
        assert body["success"] == ["obj1", "obj2"]
        assert body["failed"] == {}

    def test_handle_success_with_array_format(self, mock_storage_manager):
        """Test collection creation with direct array format"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "tabs"},
                    "headers": {},
                    "body": json.dumps(
                        [{"id": "tab1", "payload": "data1"}, {"id": "tab2", "payload": "data2"}]
                    ),
                }
            )
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
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "history"},
                    "headers": {},
                    "body": None,
                }
            )
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
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {"X-If-Unmodified-Since": "1234567889.00"},
                    "body": json.dumps({"objects": []}),
                }
            )
        )

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
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {"X-If-Unmodified-Since": "1234567891.00"},
                    "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
                }
            )
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
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {},
                    "body": "invalid json{",
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "invalid!"},
                    "headers": {},
                    "body": None,
                }
            )
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
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {},
                    "body": None,
                }
            )
        )

        mock_storage_manager.create_or_update_collection.side_effect = ConflictException("Conflict")

        response = route.handle(event)

        assert response.status_code == 409

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {},
                    "body": None,
                }
            )
        )

        mock_storage_manager.create_or_update_collection.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500

    def test_handle_x_weave_records_exceeds_limit(self, mock_storage_manager):
        """Test X-Weave-Records header exceeding limit returns 400 with code 17"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {"x-weave-records": "150"},  # Exceeds 100 limit
                    "body": json.dumps([]),
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400
        assert response.body is not None
        body = json.loads(response.body)
        assert body == 17  # CODE_SERVER_LIMIT_EXCEEDED

    def test_handle_x_weave_bytes_exceeds_limit(self, mock_storage_manager):
        """Test X-Weave-Bytes header exceeding limit returns 400 with code 17"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {"x-weave-bytes": "3000000"},  # Exceeds 2MB limit
                    "body": json.dumps([]),
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400
        assert response.body is not None
        body = json.loads(response.body)
        assert body == 17  # CODE_SERVER_LIMIT_EXCEEDED

    def test_handle_x_weave_records_invalid_format(self, mock_storage_manager):
        """Test X-Weave-Records header with invalid format returns 400"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {"x-weave-records": "invalid"},
                    "body": json.dumps([]),
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_x_weave_bytes_invalid_format(self, mock_storage_manager):
        """Test X-Weave-Bytes header with invalid format returns 400"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {"x-weave-bytes": "invalid"},
                    "body": json.dumps([]),
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_x_weave_records_mismatch(self, mock_storage_manager):
        """Test X-Weave-Records header mismatch with actual records returns 400"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {"x-weave-records": "5"},  # Says 5 records
                    "body": json.dumps([{"id": "obj1", "payload": "data"}]),  # But only 1
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_x_weave_bytes_valid(self, mock_storage_manager):
        """Test X-Weave-Bytes header with valid value proceeds normally"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {"x-weave-bytes": "1000"},  # Valid bytes
                    "body": json.dumps([{"id": "obj1", "payload": "data"}]),
                }
            )
        )

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
        mock_storage_manager.create_or_update_collection.return_value = (
            collection_data,
            batch_result,
        )

        response = route.handle(event)

        assert response.status_code == 201

    def test_handle_x_weave_records_valid_match(self, mock_storage_manager):
        """Test X-Weave-Records header matching actual records proceeds normally"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {"x-weave-records": "1"},  # Matches actual count
                    "body": json.dumps([{"id": "obj1", "payload": "data"}]),
                }
            )
        )

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
        mock_storage_manager.create_or_update_collection.return_value = (
            collection_data,
            batch_result,
        )

        response = route.handle(event)

        assert response.status_code == 201


class TestReadCollectionRoute:
    """Tests for ReadCollectionRoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the GET route and handler works through resolver"""
        # Set up mock to return empty collection
        objects = {
            "items": [],
            "more": False,
            "last_modified": 0.0,
        }
        mock_storage_manager.get_collection_objects.return_value = objects

        route = ReadCollectionRoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event = with_auth(
            {
                "httpMethod": "GET",
                "path": "/1.5/12345/storage/bookmarks",
                "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                "queryStringParameters": None,
                "headers": {},
                "body": None,
            }
        )
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_metadata_only(self, mock_storage_manager):
        """Test getting collection - returns empty list when no query params"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "queryStringParameters": None,
                    "headers": {},
                }
            )
        )

        # Now returns objects from get_collection_objects (empty list for non-existent)
        objects = {
            "items": [],
            "more": False,
            "last_modified": 1234567890.12,
        }
        mock_storage_manager.get_collection_objects.return_value = objects

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        # Mozilla-compliant: returns array of IDs (empty in this case)
        assert body == []

    def test_handle_with_object_filters(self, mock_storage_manager):
        """Test getting collection objects with filters"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "queryStringParameters": {
                        "newer": "1234567880.00",
                        "limit": "10",
                        "sort": "newest",
                        "full": "1",  # Request full objects
                    },
                    "headers": {},
                }
            )
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
        # Mozilla-compliant: returns flat array of BSO objects
        assert len(body) == 1
        assert body[0]["id"] == "obj1"

    def test_handle_objects_with_pagination(self, mock_storage_manager):
        """Test getting objects with pagination"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "history"},
                    "queryStringParameters": {"limit": "5", "offset": "10"},
                    "headers": {},
                }
            )
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
        # Mozilla-compliant: returns flat array of IDs (default full=0)
        assert len(body) == 5
        # Check X-Weave-Next-Offset header for pagination
        assert response.headers.get("X-Weave-Next-Offset") == "15"

    def test_handle_objects_without_optional_fields(self, mock_storage_manager):
        """Test formatting objects without sortindex/ttl"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "tabs"},
                    "queryStringParameters": {"ids": "obj1,obj2", "full": "1"},
                    "headers": {},
                }
            )
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
        # Mozilla-compliant: returns flat array of BSO objects
        assert "sortindex" not in body[0]
        assert "ttl" not in body[0]

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "invalid!"},
                    "queryStringParameters": None,
                    "headers": {},
                }
            )
        )

        mock_storage_manager.get_collection_objects.side_effect = ValidationException("Invalid")

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_collection_not_found(self, mock_storage_manager):
        """Test handling of non-existent collection - returns empty list per Mozilla spec"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "nonexistent"},
                    "queryStringParameters": None,
                    "headers": {},
                }
            )
        )

        # Per Mozilla spec (Requirement 2.2), return empty list for non-existent collections
        objects = {
            "items": [],
            "more": False,
            "last_modified": 0.0,
        }
        mock_storage_manager.get_collection_objects.return_value = objects

        response = route.handle(event)

        # Should return 200 with empty list, not 404
        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body == []

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "queryStringParameters": None,
                    "headers": {},
                }
            )
        )

        mock_storage_manager.get_collection_objects.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500

    def test_handle_conditional_get_not_modified(self, mock_storage_manager):
        """Test conditional GET returns 304 when not modified"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "queryStringParameters": None,
                    "headers": {"x-if-modified-since": "1234567890.12"},
                }
            )
        )

        objects = {
            "items": [],
            "more": False,
            "last_modified": 1234567880.00,  # Older than if-modified-since
        }
        mock_storage_manager.get_collection_objects.return_value = objects

        response = route.handle(event)

        assert response.status_code == 304

    def test_handle_conditional_get_modified(self, mock_storage_manager):
        """Test conditional GET returns 200 when modified"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "queryStringParameters": None,
                    "headers": {"x-if-modified-since": "1234567880.00"},
                }
            )
        )

        objects = {
            "items": [],
            "more": False,
            "last_modified": 1234567890.12,  # Newer than if-modified-since
        }
        mock_storage_manager.get_collection_objects.return_value = objects

        response = route.handle(event)

        assert response.status_code == 200

    def test_handle_both_conditional_headers_returns_400(self, mock_storage_manager):
        """Test both X-If-Modified-Since and X-If-Unmodified-Since returns 400"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "queryStringParameters": None,
                    "headers": {
                        "x-if-modified-since": "1234567890.12",
                        "x-if-unmodified-since": "1234567890.12",
                    },
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_invalid_if_modified_since_returns_400(self, mock_storage_manager):
        """Test invalid X-If-Modified-Since header returns 400"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "queryStringParameters": None,
                    "headers": {"x-if-modified-since": "invalid"},
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_negative_if_modified_since_returns_400(self, mock_storage_manager):
        """Test negative X-If-Modified-Since header returns 400"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "queryStringParameters": None,
                    "headers": {"x-if-modified-since": "-1.0"},
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_with_datetime_last_modified(self, mock_storage_manager):
        """Test handling when last_modified is a datetime object"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "queryStringParameters": None,
                    "headers": {},
                }
            )
        )

        objects = {
            "items": [],
            "more": False,
            "last_modified": datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
        }
        mock_storage_manager.get_collection_objects.return_value = objects

        response = route.handle(event)

        assert response.status_code == 200

    def test_handle_with_none_last_modified(self, mock_storage_manager):
        """Test handling when last_modified is None"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "queryStringParameters": None,
                    "headers": {},
                }
            )
        )

        objects = {
            "items": [],
            "more": False,
            "last_modified": None,  # None value
        }
        mock_storage_manager.get_collection_objects.return_value = objects

        response = route.handle(event)

        assert response.status_code == 200
        # Should default to 0.0
        assert response.headers.get("X-Last-Modified") == "0.0"


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

        event = with_auth(
            {
                "httpMethod": "PUT",
                "path": "/1.5/12345/storage/bookmarks",
                "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                "headers": {},
                "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
            }
        )
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self, mock_storage_manager):
        """Test successful collection update"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {},
                    "body": json.dumps({"objects": [{"id": "obj1", "payload": "updated"}]}),
                }
            )
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
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {},
                    "body": "invalid json{",
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_missing_objects_key(self, mock_storage_manager):
        """Test handling of missing 'objects' key in body"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {},
                    "body": json.dumps({"data": []}),
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_with_precondition_header(self, mock_storage_manager):
        """Test with X-If-Unmodified-Since header"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {"X-If-Unmodified-Since": "1234567890"},
                    "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
                }
            )
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

    def test_handle_passes_precondition_to_storage_manager(self, mock_storage_manager):
        """Test that X-If-Unmodified-Since header value is forwarded to update_collection"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {"X-If-Unmodified-Since": "1234567890"},
                    "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
                }
            )
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
        mock_storage_manager.update_collection.return_value = (collection_data, batch_result)

        response = route.handle(event)

        assert response.status_code == 200
        mock_storage_manager.update_collection.assert_called_once_with(
            TEST_USER_ID,
            collection_name="bookmarks",
            objects=ANY,
            if_unmodified_since=1234567890,
        )

    def test_handle_invalid_precondition_header(self, mock_storage_manager):
        """Test with invalid X-If-Unmodified-Since header"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {"X-If-Unmodified-Since": "invalid"},
                    "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "invalid!"},
                    "headers": {},
                    "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
                }
            )
        )

        mock_storage_manager.update_collection.side_effect = ValidationException("Invalid")

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_collection_not_found(self, mock_storage_manager):
        """Test handling of CollectionNotFoundException"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "nonexistent"},
                    "headers": {},
                    "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
                }
            )
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
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {},
                    "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
                }
            )
        )

        mock_storage_manager.update_collection.side_effect = PreconditionFailedException("Failed")

        response = route.handle(event)

        assert response.status_code == 412

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "headers": {},
                    "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
                }
            )
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

        event = with_auth(
            {
                "httpMethod": "DELETE",
                "path": "/1.5/12345/storage/bookmarks",
                "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                "queryStringParameters": None,
                "headers": {},
                "body": None,
            }
        )
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self, mock_storage_manager):
        """Test successful collection deletion"""
        route = DeleteCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "queryStringParameters": None,
                }
            )
        )

        mock_storage_manager.delete_collection.return_value = 1234567892.00

        response = route.handle(event)

        mock_storage_manager.delete_collection.assert_called_once_with(TEST_USER_ID, "bookmarks")
        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body["modified"] == 1234567892.00

    def test_handle_validation_exception(self, mock_storage_manager):
        """Test handling of ValidationException"""
        route = DeleteCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "invalid!"},
                    "queryStringParameters": None,
                }
            )
        )

        mock_storage_manager.delete_collection.side_effect = ValidationException("Invalid")

        response = route.handle(event)

        assert response.status_code == 400

    def test_handle_collection_not_found(self, mock_storage_manager):
        """Test handling of CollectionNotFoundException"""
        route = DeleteCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "nonexistent"},
                    "queryStringParameters": None,
                }
            )
        )

        mock_storage_manager.delete_collection.side_effect = CollectionNotFoundException(
            "Not found"
        )

        response = route.handle(event)

        assert response.status_code == 404

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = DeleteCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "queryStringParameters": None,
                }
            )
        )

        mock_storage_manager.delete_collection.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500

    def test_handle_selective_deletion(self, mock_storage_manager):
        """Test selective deletion with ids parameter"""
        route = DeleteCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                    "queryStringParameters": {"ids": "obj1,obj2,obj3"},
                }
            )
        )

        mock_storage_manager.delete_collection_objects.return_value = 1234567892.00

        response = route.handle(event)

        mock_storage_manager.delete_collection_objects.assert_called_once_with(
            TEST_USER_ID, "bookmarks", ["obj1", "obj2", "obj3"]
        )
        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body["modified"] == 1234567892.00


class TestListCollectionsRoute:
    """Tests for ListCollectionsRoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the GET route and handler works through resolver"""
        mock_storage_manager.list_collections.return_value = []
        route = ListCollectionsRoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event: dict[str, Any] = with_auth(
            {
                "httpMethod": "GET",
                "path": "/1.5/12345/storage",
                "pathParameters": {"uid": "12345"},
                "queryStringParameters": None,
                "headers": {},
                "body": None,
            }
        )
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self, mock_storage_manager):
        """Test successful collection listing"""
        route = ListCollectionsRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "queryStringParameters": None,
                }
            )
        )

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

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "queryStringParameters": None,
                }
            )
        )

        mock_storage_manager.list_collections.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500


class TestCreateCollectionRouteUnauthorized:
    """Tests for CreateCollectionRoute unauthorized cases"""

    def test_handle_unauthorized_missing_user_id(self, mock_storage_manager):
        """Test handling when user_id is missing from authorizer context"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                "body": json.dumps({"objects": []}),
                "headers": {},
                "requestContext": {"authorizer": {}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 401
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Unauthorized"


class TestDeleteCollectionRouteUnauthorized:
    """Tests for DeleteCollectionRoute unauthorized cases"""

    def test_handle_unauthorized_missing_user_id(self, mock_storage_manager):
        """Test handling when user_id is missing from authorizer context"""
        route = DeleteCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                "requestContext": {"authorizer": {}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 401
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Unauthorized"


class TestListCollectionsRouteUnauthorized:
    """Tests for ListCollectionsRoute unauthorized cases"""

    def test_handle_unauthorized_missing_user_id(self, mock_storage_manager):
        """Test handling when user_id is missing from authorizer context"""
        route = ListCollectionsRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "requestContext": {"authorizer": {}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 401
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Unauthorized"


class TestReadCollectionRouteUnauthorized:
    """Tests for ReadCollectionRoute unauthorized cases"""

    def test_handle_unauthorized_missing_user_id(self, mock_storage_manager):
        """Test handling when user_id is missing from authorizer context"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                "requestContext": {"authorizer": {}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 401
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Unauthorized"


class TestUpdateCollectionRouteUnauthorized:
    """Tests for UpdateCollectionRoute unauthorized cases"""

    def test_handle_unauthorized_missing_user_id(self, mock_storage_manager):
        """Test handling when user_id is missing from authorizer context"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            {
                "pathParameters": {"uid": "12345", "collectionName": "bookmarks"},
                "body": json.dumps({"objects": []}),
                "headers": {},
                "requestContext": {"authorizer": {}},
            }
        )

        response = route.handle(event)

        assert response.status_code == 401
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Unauthorized"


class TestCreateCollectionRouteInvalidCollectionName:
    """Tests that validate_collection_name is called before storage in CreateCollectionRoute"""

    def test_handle_invalid_collection_name(self, mock_storage_manager):
        """Test that invalid collection name returns 400 without calling storage"""
        route = CreateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "invalid name!"},
                    "headers": {},
                    "body": None,
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400
        mock_storage_manager.create_or_update_collection.assert_not_called()


class TestReadCollectionRouteInvalidCollectionName:
    """Tests that validate_collection_name is called before storage in ReadCollectionRoute"""

    def test_handle_invalid_collection_name(self, mock_storage_manager):
        """Test that invalid collection name returns 400 without calling storage"""
        route = ReadCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "invalid name!"},
                    "queryStringParameters": None,
                    "headers": {},
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400
        mock_storage_manager.get_collection_objects.assert_not_called()


class TestUpdateCollectionRouteInvalidCollectionName:
    """Tests that validate_collection_name is called before storage in UpdateCollectionRoute"""

    def test_handle_invalid_collection_name(self, mock_storage_manager):
        """Test that invalid collection name returns 400 without calling storage"""
        route = UpdateCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "invalid name!"},
                    "headers": {},
                    "body": json.dumps({"objects": [{"id": "obj1", "payload": "data"}]}),
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400
        mock_storage_manager.update_collection.assert_not_called()


class TestDeleteCollectionRouteInvalidCollectionName:
    """Tests that validate_collection_name is called before storage in DeleteCollectionRoute"""

    def test_handle_invalid_collection_name(self, mock_storage_manager):
        """Test that invalid collection name returns 400 without calling storage"""
        route = DeleteCollectionRoute(mock_storage_manager)

        event = APIGatewayProxyEvent(
            with_auth(
                {
                    "pathParameters": {"uid": "12345", "collectionName": "invalid name!"},
                    "queryStringParameters": None,
                }
            )
        )

        response = route.handle(event)

        assert response.status_code == 400
        mock_storage_manager.delete_collection.assert_not_called()
        mock_storage_manager.delete_collection_objects.assert_not_called()
