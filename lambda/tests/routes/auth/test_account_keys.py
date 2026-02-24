"""Unit tests for AccountKeys route"""

import json
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.account_keys import AccountKeysRoute


@pytest.fixture
def mock_account_manager():
    return MagicMock()


@pytest.fixture
def mock_token_manager():
    return MagicMock()


@pytest.fixture
def route(mock_account_manager, mock_token_manager):
    return AccountKeysRoute(
        account_manager=mock_account_manager,
        token_manager=mock_token_manager,
    )


class TestAccountKeys:
    def test_success_returns_bundle(self, route, mock_account_manager, mock_token_manager):
        token_id_hex = "aa" * 32
        raw_token_hex = "bb" * 32
        mock_token_manager.verify_keyfetch_hawk.return_value = {
            "uid": "uid1",
            "keyFetchToken": raw_token_hex,
        }
        mock_account_manager.get_account_by_uid.return_value = {
            "uid": "uid1",
            "kA": "cc" * 32,
            "wrapKB": "dd" * 32,
        }

        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/keys",
                "headers": {"authorization": f'Hawk id="{token_id_hex}"'},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert "bundle" in body
        # bundle = 64 bytes ciphertext + 32 bytes HMAC = 96 bytes = 192 hex chars
        assert len(body["bundle"]) == 192

    def test_invalid_token_returns_401(self, route, mock_token_manager):
        mock_token_manager.verify_keyfetch_hawk.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/keys",
                "headers": {"authorization": 'Hawk id="invalid"'},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_missing_auth_header_returns_401(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/keys",
                "headers": {},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_account_not_found_returns_401(self, route, mock_token_manager, mock_account_manager):
        mock_token_manager.verify_keyfetch_hawk.return_value = {
            "uid": "uid1",
            "keyFetchToken": "bb" * 32,
        }
        mock_account_manager.get_account_by_uid.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/keys",
                "headers": {"authorization": 'Hawk id="token"'},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_consumed_token_second_request_returns_401(self, route, mock_token_manager):
        mock_token_manager.verify_keyfetch_hawk.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/account/keys",
                "headers": {"authorization": 'Hawk id="consumed"'},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 401


class TestAccountKeysBind:
    def test_bind_registers_get_route(self, route):
        mock_api = MagicMock()
        mock_api.get = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.get.assert_called_once_with("/v1/account/keys")
