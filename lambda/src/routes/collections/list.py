import json

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute

logger = Logger()


class ListCollectionsRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/storage")
        def handle_request():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """List all collections with their metadata"""
        try:
            # Get collections using storage manager
            collections = self.storage_manager.list_collections()

            response_body = {
                "collections": [
                    {
                        "name": collection.name,
                        "modified": collection.modified,
                        "count": collection.count,
                        "usage": collection.usage,
                    }
                    for collection in collections
                ]
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
