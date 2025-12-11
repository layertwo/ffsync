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
        @app.get("/info/collections")
        def handle_request():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Get metadata for all collections"""
        try:
            # Get collections using storage manager
            collections = self.storage_manager.list_collections()

            # Convert to map format as expected by the Smithy model
            collections_map = {
                collection.name: {
                    "name": collection.name,
                    "modified": collection.modified,
                    "count": collection.count,
                    "usage": collection.usage,
                }
                for collection in collections
            }

            response_body = {"collections": collections_map}

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
