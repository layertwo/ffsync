"""Tests for storage route handlers"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from aws_lambda_powertools.event_handler import APIGatewayRestResolver

from src.routes.storage.delete_all import DeleteAllStorageRoute


class TestDeleteAllStorageRoute:
    """Tests for DeleteAllStorageRoute"""

    def test_bind_registers_route(self):
        """Test that bind registers the DELETE route and handler works through resolver"""
        route = DeleteAllStorageRoute()
        app = APIGatewayRestResolver()
        route.bind(app)

        event: dict[str, Any] = {
            "httpMethod": "DELETE",
            "path": "/storage",
            "pathParameters": None,
            "headers": {},
            "body": None,
            "requestContext": {},
        }
        result = app.resolve(event, MagicMock())
        assert result["statusCode"] == 200

    def test_handle_success(self):
        """Test successful deletion of all storage"""
        route = DeleteAllStorageRoute()

        event: dict[str, Any] = {}

        with patch("src.routes.storage.delete_all.get_current_timestamp") as mock_timestamp:
            mock_timestamp.return_value = 1234567890.12

            response = route.handle(event)

            mock_timestamp.assert_called_once()
            assert response.status_code == 200

            assert response.body is not None
            body = json.loads(response.body)
            assert body["modified"] == 1234567890.12

    def test_handle_with_different_timestamps(self):
        """Test that different timestamps are returned"""
        route = DeleteAllStorageRoute()

        event: dict[str, Any] = {}

        timestamps = [1234567890.12, 1234567891.50, 1234567892.75]

        for expected_timestamp in timestamps:
            with patch("src.routes.storage.delete_all.get_current_timestamp") as mock_timestamp:
                mock_timestamp.return_value = expected_timestamp

                response = route.handle(event)

                assert response.body is not None
                body = json.loads(response.body)
                assert body["modified"] == expected_timestamp

    def test_handle_generic_exception(self):
        """Test handling of generic exceptions"""
        route = DeleteAllStorageRoute()

        event: dict[str, Any] = {}

        with patch("src.routes.storage.delete_all.get_current_timestamp") as mock_timestamp:
            mock_timestamp.side_effect = Exception("Timestamp error")

            response = route.handle(event)

            assert response.status_code == 500
            assert response.body is not None
            body = json.loads(response.body)
            assert body["error"] == "Internal server error"

    def test_handle_returns_json_content_type(self):
        """Test that response has correct content type"""
        route = DeleteAllStorageRoute()

        event: dict[str, Any] = {}

        with patch("src.routes.storage.delete_all.get_current_timestamp") as mock_timestamp:
            mock_timestamp.return_value = 1234567890.12

            response = route.handle(event)

            assert response.content_type == "application/json"
