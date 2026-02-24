"""Unit tests for AccountStatus route"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.account_status import AccountStatusRoute


@pytest.fixture
def mock_account_manager():
    return MagicMock()


@pytest.fixture
def route(mock_account_manager):
    return AccountStatusRoute(account_manager=mock_account_manager)


class TestAccountStatus:
    def test_returns_true_for_existing_account(self, route, mock_account_manager):
        mock_account_manager.get_account_by_email.return_value = {"uid": "uid1"}
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/status",
                "queryStringParameters": {"email": "test@example.com"},
                "headers": {},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["exists"] is True

    def test_returns_false_for_unknown_account(self, route, mock_account_manager):
        mock_account_manager.get_account_by_email.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/status",
                "queryStringParameters": {"email": "missing@example.com"},
                "headers": {},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["exists"] is False

    def test_returns_400_for_missing_email(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/status",
                "queryStringParameters": {},
                "headers": {},
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_returns_400_for_null_query_params(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/status",
                "queryStringParameters": None,
                "headers": {},
            }
        )
        response = route.handle(event)
        assert response.status_code == 400


class TestAccountStatusBind:
    def test_bind_registers_get_route(self, route):
        mock_api = MagicMock()
        mock_api.get = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.get.assert_called_once_with("/v1/account/status")
