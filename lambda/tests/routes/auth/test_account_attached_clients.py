"""Unit tests for AccountAttachedClients route"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.account_attached_clients import AccountAttachedClientsRoute


@pytest.fixture
def device_manager():
    return MagicMock()


@pytest.fixture
def route(device_manager):
    return AccountAttachedClientsRoute(device_manager=device_manager, middlewares=[])


class TestAccountAttachedClients:
    def test_returns_attached_clients(self, route, device_manager):
        device_manager.get_devices.return_value = [
            {
                "id": "dev1",
                "name": "Desktop",
                "type": "desktop",
                "sessionTokenId": "token123",
                "createdAt": 1000,
                "lastAccessTime": 2000,
            },
        ]
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/attached_clients",
                "headers": {"authorization": 'Hawk id="token123"'},
                "queryStringParameters": {},
                "body": None,
                "requestContext": {"hawk_uid": "uid1", "hawk_token_id": "token123"},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert len(body) == 1
        client = body[0]
        assert client["clientId"] is None
        assert client["deviceId"] == "dev1"
        assert client["sessionTokenId"] == "token123"
        assert client["refreshTokenId"] is None
        assert client["deviceType"] == "desktop"
        assert client["name"] == "Desktop"
        assert client["createdTime"] == 1000
        assert client["lastAccessTime"] == 2000
        assert client["scope"] is None
        assert client["location"] == {}
        assert client["userAgent"] == ""
        assert client["os"] is None

    def test_is_current_session_set(self, route, device_manager):
        device_manager.get_devices.return_value = [
            {
                "id": "dev1",
                "sessionTokenId": "token123",
                "type": "desktop",
                "name": "A",
                "createdAt": 1000,
                "lastAccessTime": 2000,
            },
            {
                "id": "dev2",
                "sessionTokenId": "other-token",
                "type": "mobile",
                "name": "B",
                "createdAt": 1500,
                "lastAccessTime": 2500,
            },
        ]
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/attached_clients",
                "headers": {"authorization": 'Hawk id="token123"'},
                "queryStringParameters": {},
                "body": None,
                "requestContext": {"hawk_uid": "uid1", "hawk_token_id": "token123"},
            }
        )
        response = route.handle(event)
        body = json.loads(response.body)
        assert body[0]["isCurrentSession"] is True
        assert body[1]["isCurrentSession"] is False

    def test_returns_empty_list(self, route, device_manager):
        device_manager.get_devices.return_value = []
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/attached_clients",
                "headers": {"authorization": 'Hawk id="token123"'},
                "queryStringParameters": {},
                "body": None,
                "requestContext": {"hawk_uid": "uid1", "hawk_token_id": "token123"},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body == []


class TestAccountAttachedClientsBind:
    def test_bind_registers_get_route(self, route):
        mock_api = MagicMock()
        mock_api.get = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.get.assert_called_once_with("/v1/account/attached_clients", middlewares=[])
