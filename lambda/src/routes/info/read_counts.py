import json
from typing import Any

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute

logger = Logger()


class ReadCollectionCountsRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver) -> None:
        @app.get("/1.5/<uid>/info/collection_counts")
        def handle_request(uid: str) -> Response[Any]:
            return self.handle(app.current_event)

    def handle(self, event: APIGatewayProxyEvent) -> Response:
        """
        Get count information for all collections.

        Returns Mozilla format: object mapping collection names to counts directly.
        Example: {"bookmarks": 15, "tabs": 7}
        """
        try:
            user_id = self.hawk_uid(event)
            if not user_id:
                return self.unauthorized()

            # Get collections using storage manager
            collections = self.storage_manager.list_collections(user_id)

            # Mozilla format: object mapping collection names to counts directly
            response_body = {collection.name: collection.count for collection in collections}

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
