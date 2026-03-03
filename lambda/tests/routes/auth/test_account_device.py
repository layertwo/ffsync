"""Unit tests for AccountDevice route"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.account_device import AccountDeviceRoute


@pytest.fixture
def device_manager():
    return MagicMock()


@pytest.fixture
def route(device_manager):
    return AccountDeviceRoute(device_manager=device_manager, middlewares=[])


class TestAccountDevice:
    def test_create_device_returns_200(self, route, device_manager):
        device_manager.upsert_device.return_value = {
            "id": "dev1",
            "name": "My Firefox",
            "type": "desktop",
            "sessionTokenId": "token123",
            "createdAt": 1000,
            "lastAccessTime": 1000,
        }
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/device",
                "headers": {"authorization": 'Hawk id="token123"'},
                "body": json.dumps({"name": "My Firefox", "type": "desktop"}),
                "requestContext": {"hawk_uid": "uid1", "hawk_token_id": "token123"},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["id"] == "dev1"
        assert body["name"] == "My Firefox"
        device_manager.upsert_device.assert_called_once_with(
            "uid1",
            "token123",
            {"name": "My Firefox", "type": "desktop"},
        )

    def test_update_device_returns_200(self, route, device_manager):
        device_manager.upsert_device.return_value = {
            "id": "existing-dev",
            "name": "Updated Name",
            "type": "mobile",
            "sessionTokenId": "token123",
            "createdAt": 500,
            "lastAccessTime": 2000,
        }
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/device",
                "headers": {},
                "body": json.dumps(
                    {"id": "existing-dev", "name": "Updated Name", "type": "mobile"}
                ),
                "requestContext": {"hawk_uid": "uid1", "hawk_token_id": "token123"},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["id"] == "existing-dev"
        assert body["name"] == "Updated Name"
        device_manager.upsert_device.assert_called_once_with(
            "uid1",
            "token123",
            {"id": "existing-dev", "name": "Updated Name", "type": "mobile"},
        )

    def test_missing_body_returns_200(self, route, device_manager):
        device_manager.upsert_device.return_value = {
            "id": "auto-id",
            "name": "",
            "type": "desktop",
            "sessionTokenId": "token123",
            "createdAt": 3000,
            "lastAccessTime": 3000,
        }
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/device",
                "headers": {},
                "body": None,
                "requestContext": {"hawk_uid": "uid1", "hawk_token_id": "token123"},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["id"] == "auto-id"
        device_manager.upsert_device.assert_called_once_with("uid1", "token123", {})


class TestAccountDeviceBind:
    def test_bind_registers_post_route(self, route):
        mock_api = MagicMock()
        mock_api.post = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.post.assert_called_once_with("/v1/account/device", middlewares=[])
