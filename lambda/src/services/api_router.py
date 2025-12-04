from aws_lambda_powertools import Logger
from aws_lambda_proxy import API

from src.shared.base_route import BaseRoute

logger = Logger()


class ApiRouter:
    def __init__(self, routes: list[BaseRoute]):
        self.api = API(name="StorageAPI", version="1.0")
        self._routes = routes
        self._register_routes()

    def _register_routes(self):
        """Register routes by calling each route's bind method"""
        for route in self._routes:
            route.bind(self.api)

    def handler(self, event, context):
        """Main Lambda handler entry point"""
        logger.info(f"Received event: {event}")
        return self.api(event=event, context=context)
