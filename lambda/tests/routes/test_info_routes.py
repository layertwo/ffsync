"""Tests for info route handlers"""

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

from aws_lambda_powertools.event_handler import APIGatewayRestResolver

from src.routes.info.read_collections import ReadCollectionsInfoRoute
from src.routes.info.read_configuration import ReadConfigurationRoute
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

    def test_handle_success_mozilla_format(self, mock_storage_manager):
        """Test successful retrieval of collections info in Mozilla format (name -> timestamp)"""
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
        # Mozilla format: object mapping collection names to timestamps
        assert body == {
            "bookmarks": 1234567890.12,
            "history": 1234567880.00,
            "tabs": 1234567870.00,
        }

    def test_handle_empty_collections(self, mock_storage_manager):
        """Test handling when no collections exist"""
        route = ReadCollectionsInfoRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        mock_storage_manager.list_collections.return_value = []

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        # Mozilla format: empty object
        assert body == {}

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

    def test_handle_success_mozilla_format(self, mock_storage_manager):
        """Test successful retrieval of collection counts in Mozilla format (name -> count)"""
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
        # Mozilla format: object mapping collection names to counts directly
        assert body == {"bookmarks": 15, "history": 100, "tabs": 7}

    def test_handle_empty_collections(self, mock_storage_manager):
        """Test handling when no collections exist"""
        route = ReadCollectionCountsRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        mock_storage_manager.list_collections.return_value = []

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        # Mozilla format: empty object
        assert body == {}

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

    def test_handle_success_mozilla_format(self, mock_storage_manager):
        """Test successful retrieval of collection usage in Mozilla format (name -> usage in KB)"""
        route = ReadCollectionUsageRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        collections = [
            CollectionData(
                name="bookmarks",
                modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
                count=5,
                usage=1024,  # 1 KB
            ),
            CollectionData(
                name="history",
                modified=datetime.fromtimestamp(1234567880.00, tz=timezone.utc),
                count=10,
                usage=4096,  # 4 KB
            ),
            CollectionData(
                name="tabs",
                modified=datetime.fromtimestamp(1234567870.00, tz=timezone.utc),
                count=3,
                usage=512,  # 0.5 KB
            ),
        ]
        mock_storage_manager.list_collections.return_value = collections

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        # Mozilla format: object mapping collection names to usage in KB (not bytes)
        assert body == {"bookmarks": 1.0, "history": 4.0, "tabs": 0.5}

    def test_handle_empty_collections(self, mock_storage_manager):
        """Test handling when no collections exist"""
        route = ReadCollectionUsageRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        mock_storage_manager.list_collections.return_value = []

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)
        # Mozilla format: empty object
        assert body == {}

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

    def test_handle_success_mozilla_format(self, mock_storage_manager):
        """Test successful retrieval of quota information in Mozilla format [usage_kb, quota_kb]"""
        route = ReadQuotaInfoRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        collections = [
            CollectionData(
                name="bookmarks",
                modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
                count=5,
                usage=1024,  # 1 KB
            ),
            CollectionData(
                name="history",
                modified=datetime.fromtimestamp(1234567880.00, tz=timezone.utc),
                count=10,
                usage=2048,  # 2 KB
            ),
            CollectionData(
                name="tabs",
                modified=datetime.fromtimestamp(1234567870.00, tz=timezone.utc),
                count=3,
                usage=512,  # 0.5 KB
            ),
        ]
        mock_storage_manager.list_collections.return_value = collections

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)

        # Mozilla format: [usage_kb, quota_kb or null]
        assert isinstance(body, list)
        assert len(body) == 2
        # Total usage: (1024 + 2048 + 512) / 1024 = 3.5 KB
        assert body[0] == 3.5
        # Default quota is None (not enforced)
        assert body[1] is None

    def test_handle_with_quota_limit(self, mock_storage_manager):
        """Test quota info with a configured quota limit"""
        quota_kb = 10240  # 10 MB in KB
        route = ReadQuotaInfoRoute(mock_storage_manager, quota_kb=quota_kb)

        event: dict[str, Any] = with_auth({})

        collections = [
            CollectionData(
                name="bookmarks",
                modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
                count=5,
                usage=2048,  # 2 KB
            ),
        ]
        mock_storage_manager.list_collections.return_value = collections

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)

        # Mozilla format: [usage_kb, quota_kb]
        assert body[0] == 2.0  # 2048 bytes = 2 KB
        assert body[1] == 10240  # Configured quota

    def test_handle_no_collections(self, mock_storage_manager):
        """Test quota info when no collections exist"""
        route = ReadQuotaInfoRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        mock_storage_manager.list_collections.return_value = []

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)

        # Mozilla format: [usage_kb, quota_kb or null]
        assert isinstance(body, list)
        assert len(body) == 2
        assert body[0] == 0.0  # No usage
        assert body[1] is None  # No quota enforced

    def test_handle_single_collection(self, mock_storage_manager):
        """Test quota info with single collection"""
        route = ReadQuotaInfoRoute(mock_storage_manager)

        event: dict[str, Any] = with_auth({})

        collections = [
            CollectionData(
                name="bookmarks",
                modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
                count=25,
                usage=5120,  # 5 KB
            )
        ]
        mock_storage_manager.list_collections.return_value = collections

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)

        # Mozilla format: [usage_kb, quota_kb or null]
        assert body[0] == 5.0  # 5120 bytes = 5 KB
        assert body[1] is None

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


class TestReadConfigurationRoute:
    """Tests for ReadConfigurationRoute"""

    def test_bind_registers_route(self):
        """Test that bind registers the GET route and handler works through resolver"""
        route = ReadConfigurationRoute()
        app = APIGatewayRestResolver()
        route.bind(app)

        event: dict[str, Any] = {
            "httpMethod": "GET",
            "path": "/info/configuration",
            "pathParameters": None,
            "headers": {},
            "body": None,
        }
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_default_configuration(self):
        """Test successful retrieval of default server configuration"""
        route = ReadConfigurationRoute()

        event: dict[str, Any] = {}

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)

        # Required fields per Mozilla spec
        assert body["max_request_bytes"] == 2 * 1024 * 1024  # 2 MB
        assert body["max_post_records"] == 100
        assert body["max_post_bytes"] == 2 * 1024 * 1024  # 2 MB
        assert body["max_record_payload_bytes"] == 256 * 1024  # 256 KB

        # Optional fields should not be present by default
        assert "max_total_records" not in body
        assert "max_total_bytes" not in body

    def test_handle_custom_configuration(self):
        """Test configuration with custom limits"""
        route = ReadConfigurationRoute(
            max_request_bytes=1024 * 1024,  # 1 MB
            max_post_records=50,
            max_post_bytes=512 * 1024,  # 512 KB
            max_record_payload_bytes=128 * 1024,  # 128 KB
            max_total_records=1000,
            max_total_bytes=10 * 1024 * 1024,  # 10 MB
        )

        event: dict[str, Any] = {}

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)

        assert body["max_request_bytes"] == 1024 * 1024
        assert body["max_post_records"] == 50
        assert body["max_post_bytes"] == 512 * 1024
        assert body["max_record_payload_bytes"] == 128 * 1024
        assert body["max_total_records"] == 1000
        assert body["max_total_bytes"] == 10 * 1024 * 1024

    def test_handle_partial_optional_configuration(self):
        """Test configuration with only some optional limits"""
        route = ReadConfigurationRoute(
            max_total_records=500,
            max_total_bytes=None,  # Not configured
        )

        event: dict[str, Any] = {}

        response = route.handle(event)

        assert response.status_code == 200
        assert response.body is not None
        body = json.loads(response.body)

        # Required fields present
        assert "max_request_bytes" in body
        assert "max_post_records" in body
        assert "max_post_bytes" in body
        assert "max_record_payload_bytes" in body

        # Only max_total_records should be present
        assert body["max_total_records"] == 500
        assert "max_total_bytes" not in body
