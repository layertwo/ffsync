"""Authentication helpers for session Hawk verification."""

import json
from typing import Union

from aws_lambda_powertools.event_handler import Response

from src.services.fxa_token_manager import FxATokenManager
from src.shared.utils import extract_hawk_request_params


def verify_session_hawk_or_error(event, token_manager: FxATokenManager) -> Union[str, Response]:
    """Verify session Hawk authentication.

    Returns uid (str) on success, or Response(401) on failure.
    """
    headers = event.headers or {}
    auth_header = headers.get("authorization", "")
    if not auth_header:
        return _hawk_error(401, 110, "Missing or invalid authorization")

    method, path, host, port = extract_hawk_request_params(event)
    uid = token_manager.verify_session_hawk(auth_header, method, path, host, port)
    if uid is None:
        return _hawk_error(401, 110, "Invalid or expired session token")

    return uid


def _hawk_error(status: int, errno: int, message: str) -> Response:
    return Response(
        status_code=status,
        content_type="application/json",
        body=json.dumps({"code": status, "errno": errno, "message": message}),
    )
