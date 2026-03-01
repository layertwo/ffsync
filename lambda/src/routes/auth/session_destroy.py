"""SessionDestroy route — POST /v1/session/destroy"""

import json
import re

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.fxa_token_manager import FxATokenManager
from src.shared.base_route import BaseRoute
from src.shared.utils import extract_hawk_request_params

HAWK_ID_PATTERN = re.compile(r'id="([^"]+)"')


class SessionDestroyRoute(BaseRoute):
    """Destroy a session token (sign out)."""

    def __init__(self, token_manager: FxATokenManager):
        self._token_manager = token_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/v1/session/destroy")
        def handle_session_destroy():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        headers = event.headers or {}
        auth_header = headers.get("authorization", "")
        if not auth_header:
            return self._error(401, 110, "Missing or invalid authorization")

        method, path, host, port = extract_hawk_request_params(event)

        uid = self._token_manager.verify_session_hawk(auth_header, method, path, host, port)
        if uid is None:
            return self._error(401, 110, "Invalid or expired session token")

        # Extract token id from Hawk header for deletion
        match = HAWK_ID_PATTERN.search(auth_header)
        if match:  # pragma: no branch
            token_id_hex = match.group(1)
            self._token_manager.delete_session(token_id_hex)

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps({}),
        )

    @staticmethod
    def _error(status: int, errno: int, message: str) -> Response:
        return Response(
            status_code=status,
            content_type="application/json",
            body=json.dumps({"code": status, "errno": errno, "message": message}),
        )
