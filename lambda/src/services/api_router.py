import json
from typing import Any, Sequence

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, CORSConfig, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler
from aws_lambda_powertools.event_handler.openapi.exceptions import (
    RequestValidationError,
    ResponseValidationError,
)
from aws_lambda_powertools.utilities.typing import LambdaContext

from src.shared.base_route import BaseRoute


class ApiRouter:
    def __init__(
        self,
        routes: list[BaseRoute],
        middlewares: Sequence[BaseMiddlewareHandler[Any]],
        cors: CORSConfig | None = None,
        exception_handlers: dict[type[Exception], Any] | None = None,
        enable_validation: bool = False,
    ):
        self.app = APIGatewayRestResolver(cors=cors, enable_validation=enable_validation)
        self._routes = routes
        self._middlewares = middlewares

        self._register_exception_handlers(exception_handlers or {})
        self._register_middleware()
        self._register_routes()

    def _register_exception_handlers(self, handlers: dict):
        for exc_type, handler_fn in handlers.items():
            self.app.exception_handler(exc_type)(handler_fn)

        @self.app.exception_handler(RequestValidationError)
        def _handle_request_validation(ex: RequestValidationError):  # pragma: nocover
            return Response(
                status_code=422,
                content_type="application/json",
                body=json.dumps({"error": "Validation error", "details": ex.errors()}),
            )

        @self.app.exception_handler(ResponseValidationError)
        def _handle_response_validation(ex: ResponseValidationError):  # pragma: nocover
            return Response(
                status_code=500,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )

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
