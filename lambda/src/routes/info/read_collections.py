import json

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute

logger = Logger()


class ReadCollectionsInfoRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/1.5/<uid>/info/collections")
        def handle_request(uid: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """
        Get metadata for all collections.

        Returns Mozilla format: object mapping collection names to timestamps.
        Example: {"bookmarks": 1234567890.12, "tabs": 1234567880.00}
        """
        try:
            # Extract user_id from authorizer context
            user_id = event.get("requestContext", {}).get("hawk_uid")
            if not user_id:
                return Response(
                    status_code=401,
                    content_type="application/json",
                    body=json.dumps({"error": "Unauthorized"}),
                )

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
