"""Tests for info route handlers"""

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

from aws_lambda_powertools.event_handler import APIGatewayRestResolver

from src.routes.info.read_collections import ReadCollectionsInfoRoute
from src.routes.info.read_counts import ReadCollectionCountsRoute
from src.routes.info.read_quota import ReadQuotaInfoRoute
from src.routes.info.read_usage import ReadCollectionUsageRoute
from src.shared.models import CollectionData

TEST_USER_ID = "test-user-123"


def with_auth(event_dict: dict) -> dict:
    """Add authorizer context to event dict"""
    if "requestContext" not in event_dict:
        event_dict["requestContext"] = {}
    event_dict["requestContext"]["authorizer"] = {"user_id": TEST_USER_ID}
    return event_dict


class TestReadCollectionsInfoRoute:
    """Tests for ReadCollectionsInfoRoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the GET route and handler works through resolver"""
        mock_storage_manager.list_collections.return_value = []
        route = ReadCollectionsInfoRoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event: dict[str, Any] = with_auth(
            {
                "httpMethod": "GET",
                "path": "/info/collections",
                "pathParameters": None,
                "headers": {},
                "body": None,
            }
        )
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self, mock_storage_manager):
        """Test successful retrieval of collections info"""
        route = ReadCollectionsInfoRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

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
            CollectionData(
                name="tabs",
                modified=datetime.fromtimestamp(1234567870.00, tz=timezone.utc),
                count=3,
                usage=512,
            ),
        ]
        mock_storage_manager.list_collections.return_value = collections

        response = route.handle(event)

        mock_storage_manager.list_collections.assert_called_once()
        assert response.status_code == 200

        assert response.body is not None
        body = json.loads(response.body)
        assert "collections" in body
        assert "bookmarks" in body["collections"]
        assert body["collections"]["bookmarks"]["name"] == "bookmarks"
        assert body["collections"]["bookmarks"]["modified"] == 1234567890.12
        assert body["collections"]["bookmarks"]["count"] == 5
        assert body["collections"]["bookmarks"]["usage"] == 1024
        assert len(body["collections"]) == 3

    def test_handle_empty_collections(self, mock_storage_manager):
        """Test handling when no collections exist"""
        route = ReadCollectionsInfoRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        mock_storage_manager.list_collections.return_value = []

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body["collections"] == {}

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = ReadCollectionsInfoRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        mock_storage_manager.list_collections.side_effect = Exception("Database error")

        response = route.handle(event)

        assert response.status_code == 500
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Internal server error"


class TestReadCollectionCountsRoute:
    """Tests for ReadCollectionCountsRoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the GET route and handler works through resolver"""
        mock_storage_manager.list_collections.return_value = []
        route = ReadCollectionCountsRoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event: dict[str, Any] = with_auth(
            {
                "httpMethod": "GET",
                "path": "/info/collection_counts",
                "pathParameters": None,
                "headers": {},
                "body": None,
            }
        )
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self, mock_storage_manager):
        """Test successful retrieval of collection counts"""
        route = ReadCollectionCountsRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        collections = [
            CollectionData(
                name="bookmarks",
                modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
                count=15,
                usage=1024,
            ),
            CollectionData(
                name="history",
                modified=datetime.fromtimestamp(1234567880.00, tz=timezone.utc),
                count=100,
                usage=2048,
            ),
            CollectionData(
                name="tabs",
                modified=datetime.fromtimestamp(1234567870.00, tz=timezone.utc),
                count=7,
                usage=512,
            ),
        ]
        mock_storage_manager.list_collections.return_value = collections

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body["counts"] == {"bookmarks": 15, "history": 100, "tabs": 7}

    def test_handle_empty_collections(self, mock_storage_manager):
        """Test handling when no collections exist"""
        route = ReadCollectionCountsRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        mock_storage_manager.list_collections.return_value = []

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body["counts"] == {}

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = ReadCollectionCountsRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        mock_storage_manager.list_collections.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500


class TestReadCollectionUsageRoute:
    """Tests for ReadCollectionUsageRoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the GET route and handler works through resolver"""
        mock_storage_manager.list_collections.return_value = []
        route = ReadCollectionUsageRoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event: dict[str, Any] = with_auth(
            {
                "httpMethod": "GET",
                "path": "/info/collection_usage",
                "pathParameters": None,
                "headers": {},
                "body": None,
            }
        )
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self, mock_storage_manager):
        """Test successful retrieval of collection usage"""
        route = ReadCollectionUsageRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

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
                usage=4096,
            ),
            CollectionData(
                name="tabs",
                modified=datetime.fromtimestamp(1234567870.00, tz=timezone.utc),
                count=3,
                usage=512,
            ),
        ]
        mock_storage_manager.list_collections.return_value = collections

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body["usage"] == {"bookmarks": 1024, "history": 4096, "tabs": 512}

    def test_handle_empty_collections(self, mock_storage_manager):
        """Test handling when no collections exist"""
        route = ReadCollectionUsageRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        mock_storage_manager.list_collections.return_value = []

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        assert body["usage"] == {}

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = ReadCollectionUsageRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        mock_storage_manager.list_collections.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500


class TestReadQuotaInfoRoute:
    """Tests for ReadQuotaInfoRoute"""

    def test_bind_registers_route(self, mock_storage_manager):
        """Test that bind registers the GET route and handler works through resolver"""
        mock_storage_manager.list_collections.return_value = []
        route = ReadQuotaInfoRoute(mock_storage_manager)
        app = APIGatewayRestResolver()
        route.bind(app)

        event: dict[str, Any] = with_auth(
            {
                "httpMethod": "GET",
                "path": "/info/quota",
                "pathParameters": None,
                "headers": {},
                "body": None,
            }
        )
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self, mock_storage_manager):
        """Test successful retrieval of quota information"""
        route = ReadQuotaInfoRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

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
            CollectionData(
                name="tabs",
                modified=datetime.fromtimestamp(1234567870.00, tz=timezone.utc),
                count=3,
                usage=512,
            ),
        ]
        mock_storage_manager.list_collections.return_value = collections

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)

        quota = body["quota"]
        assert quota["max_collections"] == 100
        assert quota["max_usage"] == 10485760
        assert quota["current_collections"] == 3
        assert quota["current_usage"] == 3584  # 1024 + 2048 + 512

    def test_handle_no_collections(self, mock_storage_manager):
        """Test quota info when no collections exist"""
        route = ReadQuotaInfoRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        mock_storage_manager.list_collections.return_value = []

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)

        quota = body["quota"]
        assert quota["current_collections"] == 0
        assert quota["current_usage"] == 0

    def test_handle_single_collection(self, mock_storage_manager):
        """Test quota info with single collection"""
        route = ReadQuotaInfoRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        collections = [
            CollectionData(
                name="bookmarks",
                modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
                count=25,
                usage=5000,
            )
        ]
        mock_storage_manager.list_collections.return_value = collections

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)

        quota = body["quota"]
        assert quota["current_collections"] == 1
        assert quota["current_usage"] == 5000

    def test_handle_generic_exception(self, mock_storage_manager):
        """Test handling of generic exceptions"""
        route = ReadQuotaInfoRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        mock_storage_manager.list_collections.side_effect = Exception("Error")

        response = route.handle(event)

        assert response.status_code == 500

    def test_handle_unauthorized_missing_user_id(self, mock_storage_manager):
        """Test handling when user_id is missing from authorizer context"""
        route = ReadQuotaInfoRoute(mock_storage_manager)

        event: dict[str, Any] = {"requestContext": {"authorizer": {}}}

        response = route.handle(event)

        assert response.status_code == 401
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Unauthorized"


class TestReadCollectionsInfoRouteUnauthorized:
    """Tests for ReadCollectionsInfoRoute unauthorized cases"""

    def test_handle_unauthorized_missing_user_id(self, mock_storage_manager):
        """Test handling when user_id is missing from authorizer context"""
        route = ReadCollectionsInfoRoute(mock_storage_manager)

        event: dict[str, Any] = {"requestContext": {"authorizer": {}}}

        response = route.handle(event)

        assert response.status_code == 401
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Unauthorized"


class TestReadCollectionCountsRouteUnauthorized:
    """Tests for ReadCollectionCountsRoute unauthorized cases"""

    def test_handle_unauthorized_missing_user_id(self, mock_storage_manager):
        """Test handling when user_id is missing from authorizer context"""
        route = ReadCollectionCountsRoute(mock_storage_manager)

        event: dict[str, Any] = {"requestContext": {"authorizer": {}}}

        response = route.handle(event)

        assert response.status_code == 401
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Unauthorized"


class TestReadCollectionUsageRouteUnauthorized:
    """Tests for ReadCollectionUsageRoute unauthorized cases"""

    def test_handle_unauthorized_missing_user_id(self, mock_storage_manager):
        """Test handling when user_id is missing from authorizer context"""
        route = ReadCollectionUsageRoute(mock_storage_manager)

        event: dict[str, Any] = {"requestContext": {"authorizer": {}}}

        response = route.handle(event)

        assert response.status_code == 401
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "Unauthorized"
