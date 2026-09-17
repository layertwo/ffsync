import json
from typing import Any

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute

logger = Logger()


class ReadCollectionsInfoRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver) -> None:
        @app.get("/1.5/<uid>/info/collections")
        def handle_request(uid: str) -> Response[Any]:
            return self.handle(app.current_event)

    def handle(self, event: APIGatewayProxyEvent) -> Response:
        """
        Get metadata for all collections.

        Returns Mozilla format: object mapping collection names to timestamps.
        Example: {"bookmarks": 1234567890.12, "tabs": 1234567880.00}
        """
        try:
            user_id = self.hawk_uid(event)
            if not user_id:
                return self.unauthorized()

            # Get collections using storage manager
            collections = self.storage_manager.list_collections(user_id)

            # Mozilla format: object mapping collection names to timestamps
            response_body = {
                collection.name: round(collection.modified, 2) for collection in collections
            }

            return Response(
                status_code=200,
                content_type="application/json",
                body=json.dumps(response_body),
            )

        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=500,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )
