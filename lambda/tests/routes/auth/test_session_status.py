"""Unit tests for SessionStatus route"""

from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.session_status import SessionStatusRoute
from tests.conftest import json_body


@pytest.fixture
def route() -> SessionStatusRoute:
    return SessionStatusRoute(middlewares=[])


class TestSessionStatus:
    def test_success_returns_state_and_uid(self, route: SessionStatusRoute) -> None:
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/session/status",
                "headers": {"authorization": 'Hawk id="tokenid"'},
                "body": None,
                "requestContext": {"hawk_uid": "uid1"},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json_body(response)
        assert body["state"] == "verified"
        assert body["uid"] == "uid1"


class TestSessionStatusBind:
    def test_bind_registers_get_route(self, route: SessionStatusRoute) -> None:
        mock_api = MagicMock()
        mock_api.get = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.get.assert_called_once_with("/v1/session/status", middlewares=[])
