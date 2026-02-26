"""Unit tests for ScopedKeyData route"""

import json
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.scoped_key_data import ScopedKeyDataRoute


@pytest.fixture
def mock_account_manager():
    return MagicMock()


@pytest.fixture
def mock_token_manager():
    return MagicMock()


@pytest.fixture
def route(mock_account_manager, mock_token_manager):
    return ScopedKeyDataRoute(
        account_manager=mock_account_manager,
        token_manager=mock_token_manager,
    )


class TestScopedKeyData:
    def test_success_returns_key_data(self, route, mock_token_manager, mock_account_manager):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        mock_account_manager.get_account_by_uid.return_value = {
            "uid": "uid1",
            "createdAt": 1234567890,
            "keyRotationSecret": "ab" * 32,
        }
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/scoped-key-data",
                "headers": {"authorization": 'Hawk id="tokenid"'},
                "body": json.dumps(
                    {
                        "client_id": "client1",
                        "scope": "https://identity.mozilla.com/apps/oldsync",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        scope_key = "https://identity.mozilla.com/apps/oldsync"
        assert scope_key in body
        assert body[scope_key]["identifier"] == scope_key
        assert body[scope_key]["keyRotationTimestamp"] == 1234567890
        assert body[scope_key]["keyRotationSecret"] == "ab" * 32

    def test_missing_auth_returns_401(self, route):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/scoped-key-data",
                "headers": {},
                "body": json.dumps({"client_id": "c", "scope": "s"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, route, mock_token_manager):
        mock_token_manager.verify_session_hawk.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/scoped-key-data",
                "headers": {"authorization": 'Hawk id="bad"'},
                "body": json.dumps({"client_id": "c", "scope": "s"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_missing_body_returns_400(self, route, mock_token_manager):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/scoped-key-data",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": None,
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_invalid_json_body_returns_400(self, route, mock_token_manager):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/scoped-key-data",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": "not-json",
            }
        )
        response = route.handle(event)
        assert response.status_code == 400

    def test_account_not_found_returns_401(self, route, mock_token_manager, mock_account_manager):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        mock_account_manager.get_account_by_uid.return_value = None
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/scoped-key-data",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": json.dumps({"client_id": "c", "scope": "s"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 401

    def test_handles_decimal_created_at_from_dynamodb(
        self, route, mock_token_manager, mock_account_manager
    ):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        mock_account_manager.get_account_by_uid.return_value = {
            "uid": "uid1",
            "createdAt": Decimal("1234567890"),
            "keyRotationSecret": "ab" * 32,
        }
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/scoped-key-data",
                "headers": {"authorization": 'Hawk id="tokenid"'},
                "body": json.dumps(
                    {
                        "client_id": "client1",
                        "scope": "https://identity.mozilla.com/apps/oldsync",
                    }
                ),
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        scope_key = "https://identity.mozilla.com/apps/oldsync"
        assert body[scope_key]["keyRotationTimestamp"] == 1234567890.0

    def test_missing_scope_returns_400(self, route, mock_token_manager):
        mock_token_manager.verify_session_hawk.return_value = "uid1"
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/account/scoped-key-data",
                "headers": {"authorization": 'Hawk id="tok"'},
                "body": json.dumps({"client_id": "c"}),
            }
        )
        response = route.handle(event)
        assert response.status_code == 400


class TestScopedKeyDataBind:
    def test_bind_registers_post_route(self, route):
        mock_api = MagicMock()
        mock_api.post = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.post.assert_called_once_with("/v1/account/scoped-key-data")
