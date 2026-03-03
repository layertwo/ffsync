"""Unit tests for AccountDevices route"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.account_devices import AccountDevicesRoute


@pytest.fixture
def device_manager():
    return MagicMock()


@pytest.fixture
def route(device_manager):
    return AccountDevicesRoute(device_manager=device_manager, middlewares=[])


class TestAccountDevices:
    def test_returns_device_list(self, route, device_manager):
        device_manager.get_devices.return_value = [
            {
                "id": "dev1",
                "name": "Desktop",
                "type": "desktop",
                "sessionTokenId": "token123",
                "createdAt": 1000,
                "lastAccessTime": 2000,
            },
            {
                "id": "dev2",
                "name": "Mobile",
                "type": "mobile",
                "sessionTokenId": "other-token",
                "createdAt": 1500,
                "lastAccessTime": 2500,
            },
        ]
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/devices",
                "headers": {"authorization": 'Hawk id="token123"'},
                "queryStringParameters": {},
                "body": None,
                "requestContext": {"hawk_uid": "uid1", "hawk_token_id": "token123"},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert len(body) == 2
        assert body[0]["isCurrentDevice"] is True
        assert body[1]["isCurrentDevice"] is False
        device_manager.get_devices.assert_called_once_with("uid1", None)

    def test_filters_idle_devices(self, route, device_manager):
        device_manager.get_devices.return_value = []
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/devices",
                "headers": {"authorization": 'Hawk id="token123"'},
                "queryStringParameters": {"filterIdleDevicesTimestamp": "1609459200000"},
                "body": None,
                "requestContext": {"hawk_uid": "uid1", "hawk_token_id": "token123"},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        device_manager.get_devices.assert_called_once_with("uid1", 1609459200000)

    def test_returns_empty_list(self, route, device_manager):
        device_manager.get_devices.return_value = []
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/devices",
                "headers": {"authorization": 'Hawk id="token123"'},
                "queryStringParameters": None,
                "body": None,
                "requestContext": {"hawk_uid": "uid1", "hawk_token_id": "token123"},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body == []


class TestAccountDevicesBind:
    def test_bind_registers_get_route(self, route):
        mock_api = MagicMock()
        mock_api.get = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.get.assert_called_once_with("/v1/account/devices", middlewares=[])
