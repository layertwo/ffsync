from typing import Any, Sequence

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, CORSConfig
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler
from aws_lambda_powertools.utilities.typing import LambdaContext

from src.middlewares.hawk_auth import HawkAuthenticationError, HawkAuthMiddleware, UidMismatchError
from src.middlewares.request_logging import RequestLoggingMiddleware
from src.middlewares.weave_timestamp import WeaveTimestampMiddleware
from src.shared.base_route import BaseRoute

__all__ = [
    "ApiRouter",
    "HawkAuthMiddleware",
    "HawkAuthenticationError",
    "RequestLoggingMiddleware",
    "UidMismatchError",
    "WeaveTimestampMiddleware",
]


class ApiRouter:
    def __init__(
        self,
        routes: list[BaseRoute],
        middlewares: Sequence[BaseMiddlewareHandler[Any]],
        cors: CORSConfig | None = None,
        exception_handlers: dict[type[Exception], Any] | None = None,
    ):
        self.app = APIGatewayRestResolver(cors=cors)
        self._routes = routes
        self._middlewares = middlewares

        self._register_exception_handlers(exception_handlers or {})
        self._register_middleware()
        self._register_routes()

    def _register_exception_handlers(self, handlers: dict):
        for exc_type, handler_fn in handlers.items():
            self.app.exception_handler(exc_type)(handler_fn)

    def _register_middleware(self):
        """Register middleware handlers"""
        self.app.use(middlewares=self._middlewares)  # type: ignore

    def _register_routes(self):
        """Register routes by calling each route's bind method"""
        for route in self._routes:
            route.bind(self.app)

    def handler(self, event: dict, context: LambdaContext):
        """Main Lambda handler entry point"""
        return self.app.resolve(event=event, context=context)
