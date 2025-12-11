from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.utilities.typing import LambdaContext

from src.shared.base_route import BaseRoute

logger = Logger()


class ApiRouter:
    def __init__(self, routes: list[BaseRoute]):
        self.app = APIGatewayRestResolver()
        self._routes = routes
        self._register_routes()

    def _register_routes(self):
        """Register routes by calling each route's bind method"""
        for route in self._routes:
            route.bind(self.app)

    def handler(self, event: dict, context: LambdaContext):
        """Main Lambda handler entry point"""
        return self.app.resolve(event=event, context=context)
