from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler, NextMiddleware
from aws_lambda_powertools.utilities.typing import LambdaContext

from src.shared.base_route import BaseRoute
from src.shared.utils import get_weave_timestamp

logger = Logger()


class WeaveTimestampMiddleware(BaseMiddlewareHandler):
    """
    Middleware that adds X-Weave-Timestamp header to all responses.

    Requirements: 9.1-9.4
    """

    def handler(self, app: APIGatewayRestResolver, next_middleware: NextMiddleware) -> Response:
        # Call the next middleware/handler in the chain
        response = next_middleware(app)

        # Add X-Weave-Timestamp header to the response
        response.headers["X-Weave-Timestamp"] = get_weave_timestamp()

        return response


class ApiRouter:
    def __init__(self, routes: list[BaseRoute]):
        self.app = APIGatewayRestResolver()
        self._routes = routes
        self._register_middleware()
        self._register_routes()

    def _register_middleware(self):
        """Register middleware handlers"""
        self.app.use(middlewares=[WeaveTimestampMiddleware()])

    def _register_routes(self):
        """Register routes by calling each route's bind method"""
        for route in self._routes:
            route.bind(self.app)

    def handler(self, event: dict, context: LambdaContext):
        """Main Lambda handler entry point"""
        return self.app.resolve(event=event, context=context)
