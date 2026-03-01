"""SessionStatus route — GET /v1/session/status"""

import json

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.fxa_token_manager import FxATokenManager
from src.shared.auth import verify_session_hawk_or_error
from src.shared.base_route import BaseRoute


class SessionStatusRoute(BaseRoute):
    """Check session token validity and return state."""

    def __init__(self, token_manager: FxATokenManager):
        self._token_manager = token_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/v1/session/status")
        def handle_session_status():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        result = verify_session_hawk_or_error(event, self._token_manager)
        if isinstance(result, Response):
            return result
        uid = result

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps({"state": "verified", "uid": uid}),
        )
