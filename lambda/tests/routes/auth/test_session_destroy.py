"""Unit tests for SessionDestroy route"""

from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.routes.auth.session_destroy import SessionDestroyRoute
from src.services.fxa_token_manager import FxATokenManager
from tests.conftest import json_body


@pytest.fixture
def route(mock_token_manager: MagicMock) -> SessionDestroyRoute:
    return SessionDestroyRoute(token_manager=mock_token_manager, middlewares=[])


class TestSessionDestroy:
    def test_success_deletes_session(
        self, route: SessionDestroyRoute, mock_token_manager: MagicMock
    ) -> None:
        # Route delegates parsing to FxATokenManager; use the real parser so the
        # assertion still proves the parsed id reaches delete_session.
        mock_token_manager.extract_token_id_from_hawk_header.side_effect = (
            FxATokenManager.extract_token_id_from_hawk_header
        )
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/session/destroy",
                "headers": {"authorization": 'Hawk id="tokenid", ts="123", nonce="abc", mac="xyz"'},
                "body": None,
                "requestContext": {"hawk_uid": "uid1"},
            }
        )
        response = route.handle(event)
        assert response.status_code == 200
        body = json_body(response)
        assert body == {}
        mock_token_manager.delete_session.assert_called_once_with("tokenid")


class TestSessionDestroyBind:
    def test_bind_registers_post_route(self, route: SessionDestroyRoute) -> None:
        mock_api = MagicMock()
        mock_api.post = MagicMock(return_value=lambda f: f)
        route.bind(mock_api)
        mock_api.post.assert_called_once_with("/v1/session/destroy", middlewares=[])
