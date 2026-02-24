"""Unit tests for AccountProfile route"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.account_profile import AccountProfileRoute


@pytest.fixture
def mock_account_manager():
    return MagicMock()


@pytest.fixture
def mock_token_manager():
    return MagicMock()


@pytest.fixture
def route(mock_account_manager, mock_token_manager):
    return AccountProfileRoute(
        account_manager=mock_account_manager,
        token_manager=mock_token_manager,
    )


class TestAccountProfile:
    def test_success_with_session_token(self, route, mock_account_manager, mock_token_manager):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        mock_account_manager.get_account_by_uid.return_value = {
            "uid": "uid1",
            "email": "user@example.com",
        }
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/profile",
                "headers": {"authorization": 'Hawk id="aa" * 32'},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["email"] == "user@example.com"
        assert body["uid"] == "uid1"
        assert body["locale"] == "en-US"

    def test_missing_auth_returns_401(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/profile",
                "headers": {},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_invalid_session_token_returns_401(self, route, mock_token_manager):
        mock_token_manager.verify_session_hawk.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/profile",
                "headers": {"authorization": 'Hawk id="invalid"'},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_account_not_found_returns_401(self, route, mock_token_manager, mock_account_manager):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        mock_account_manager.get_account_by_uid.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/profile",
                "headers": {"authorization": 'Hawk id="aa"'},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 401


class TestAccountProfileBind:
    def test_bind_registers_get_route(self, route):
        mock_api = MagicMock()
        mock_api.get = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.get.assert_called_once_with("/v1/account/profile")
