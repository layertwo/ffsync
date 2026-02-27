"""SessionStatus route — GET /v1/session/status"""

import json

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.fxa_token_manager import FxATokenManager
from src.shared.base_route import BaseRoute
from src.shared.utils import extract_hawk_request_params


class SessionStatusRoute(BaseRoute):
    """Check session token validity and return state."""

    def __init__(self, token_manager: FxATokenManager):
        self._token_manager = token_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/v1/session/status")
        def handle_session_status():
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

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps({"state": "verified", "uid": uid}),
        )

    @staticmethod
    def _error(status: int, errno: int, message: str) -> Response:
        return Response(
            status_code=status,
            content_type="application/json",
            body=json.dumps({"code": status, "errno": errno, "message": message}),
        )
