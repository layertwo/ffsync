"""Unit tests for AccountDevicesNotify route"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.account_devices_notify import AccountDevicesNotifyRoute
from tests.conftest import json_body


@pytest.fixture
def route() -> AccountDevicesNotifyRoute:
    return AccountDevicesNotifyRoute(middlewares=[])


class TestAccountDevicesNotify:
    def test_returns_empty_object(self, route: AccountDevicesNotifyRoute) -> None:
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/devices/notify",
                "headers": {"authorization": 'Hawk id="token123"'},
                "body": json.dumps({"to": "all", "payload": {}}),
                "requestContext": {"hawk_uid": "uid1"},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json_body(response)
        assert body == {}


class TestAccountDevicesNotifyBind:
    def test_bind_registers_post_route(self, route: AccountDevicesNotifyRoute) -> None:
        mock_api = MagicMock()
        mock_api.post = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.post.assert_called_once_with("/v1/account/devices/notify", middlewares=[])
