from abc import ABC, abstractmethod

from aws_lambda_powertools.event_handler import APIGatewayRestResolver


class BaseRoute(ABC):
    """Base class for all route handlers"""

    @abstractmethod
    def bind(self, app: APIGatewayRestResolver):
        """Bind this route to the API with appropriate decorators"""
        pass  # pragma: nocover

    @abstractmethod
    def handle(self, event):
        """Handle the route request"""
        pass  # pragma: nocover
