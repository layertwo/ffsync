"""Weave timestamp middleware.

Adds X-Weave-Timestamp header to all responses.
"""

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler, NextMiddleware

from src.shared.utils import get_weave_timestamp


class WeaveTimestampMiddleware(BaseMiddlewareHandler):

    def handler(self, app: APIGatewayRestResolver, next_middleware: NextMiddleware) -> Response:
        response = next_middleware(app)
        response.headers["X-Weave-Timestamp"] = get_weave_timestamp()
        return response
