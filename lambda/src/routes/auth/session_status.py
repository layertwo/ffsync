"""SessionStatus route — GET /v1/session/status"""

from typing import Sequence

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler

from src.shared.base_route import BaseRoute
from src.shared.models import SessionStatusOutput


class SessionStatusRoute(BaseRoute):
    """Check session token validity and return state."""

    def __init__(self, middlewares: Sequence[BaseMiddlewareHandler] = ()):
        self.middlewares = middlewares

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/v1/session/status", middlewares=list(self.middlewares))
        def handle_session_status():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        uid = event["requestContext"]["hawk_uid"]

        result = SessionStatusOutput(state="verified", uid=uid)
        return Response(
            status_code=200,
            content_type="application/json",
            body=result.model_dump_json(),
        )
