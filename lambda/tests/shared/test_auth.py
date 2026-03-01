"""Tests for shared auth helper (verify_session_hawk_or_error)"""

import json
from unittest.mock import MagicMock

from aws_lambda_powertools.event_handler import Response
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.shared.auth import verify_session_hawk_or_error


def _make_event(auth_header=None):
    """Build a minimal APIGatewayProxyEvent for testing."""
    headers = {}
    if auth_header is not None:
        headers["authorization"] = auth_header
    return APIGatewayProxyEvent(
        {
            "httpMethod": "GET",
            "path": "/v1/session/status",
            "headers": headers,
            "body": None,
        }
    )


class TestVerifySessionHawkOrError:
    def test_success_returns_uid_string(self):
        """Successful verification returns uid as a string."""
        mock_tm = MagicMock()
        mock_tm.verify_session_hawk.return_value = "uid123"

        event = _make_event(auth_header='Hawk id="tokenid"')
        result = verify_session_hawk_or_error(event, mock_tm)

        assert result == "uid123"
        mock_tm.verify_session_hawk.assert_called_once()

    def test_missing_auth_header_returns_401(self):
        """Missing authorization header returns Response(401)."""
        mock_tm = MagicMock()

        event = _make_event(auth_header=None)
        result = verify_session_hawk_or_error(event, mock_tm)

        assert isinstance(result, Response)
        assert result.status_code == 401
        body = json.loads(result.body)
        assert body["errno"] == 110
        mock_tm.verify_session_hawk.assert_not_called()

    def test_empty_auth_header_returns_401(self):
        """Empty authorization header returns Response(401)."""
        mock_tm = MagicMock()

        event = _make_event(auth_header="")
        result = verify_session_hawk_or_error(event, mock_tm)

        assert isinstance(result, Response)
        assert result.status_code == 401
        mock_tm.verify_session_hawk.assert_not_called()

    def test_invalid_token_returns_401(self):
        """verify_session_hawk returning None yields Response(401)."""
        mock_tm = MagicMock()
        mock_tm.verify_session_hawk.return_value = None

        event = _make_event(auth_header='Hawk id="bad"')
        result = verify_session_hawk_or_error(event, mock_tm)

        assert isinstance(result, Response)
        assert result.status_code == 401
        body = json.loads(result.body)
        assert body["errno"] == 110
        assert "expired" in body["message"].lower() or "invalid" in body["message"].lower()
