"""SessionDestroy route — POST /v1/session/destroy"""

import json
import re
from typing import Sequence

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler

from src.services.fxa_token_manager import FxATokenManager
from src.shared.base_route import BaseRoute

HAWK_ID_PATTERN = re.compile(r'id="([^"]+)"')


class SessionDestroyRoute(BaseRoute):
    """Destroy a session token (sign out)."""

    def __init__(
        self,
        token_manager: FxATokenManager,
        middlewares: Sequence[BaseMiddlewareHandler] = (),
    ):
        self._token_manager = token_manager
        self.middlewares = middlewares

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/v1/session/destroy", middlewares=list(self.middlewares))
        def handle_session_destroy():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        # Extract token id from Hawk header for deletion
        headers = event.headers or {}
        auth_header = headers.get("authorization", "")
        match = HAWK_ID_PATTERN.search(auth_header)
        if match:  # pragma: no branch
            token_id_hex = match.group(1)
            self._token_manager.delete_session(token_id_hex)

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps({}),
        )
