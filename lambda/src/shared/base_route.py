import json
from abc import ABC, abstractmethod
from typing import Sequence

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent


class BaseRoute(ABC):
    """Base class for all route handlers."""

    middlewares: Sequence[BaseMiddlewareHandler] = ()

    @abstractmethod
    def bind(self, app: APIGatewayRestResolver) -> None:
        """Bind this route to the API with appropriate decorators"""
        pass  # pragma: nocover

    @abstractmethod
    def handle(self, event: APIGatewayProxyEvent) -> Response:
        """Handle the route request"""
        pass  # pragma: nocover

    @staticmethod
    def hawk_uid(event: APIGatewayProxyEvent) -> str | None:
        """Authenticated user id injected by HawkAuthMiddleware; None if absent."""
        return (event.get("requestContext") or {}).get("hawk_uid")

    @staticmethod
    def unauthorized() -> Response:
        """The 401 every storage route returns when no authenticated user is present."""
        return Response(
            status_code=401,
            content_type="application/json",
            body=json.dumps({"error": "Unauthorized"}),
        )
