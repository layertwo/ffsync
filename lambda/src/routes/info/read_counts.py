from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.utils import json_dumps

logger = Logger()


class ReadCollectionCountsRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/info/collection_counts")
        def handle_request():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Get count information for all collections"""
        try:
            # Get collections using storage manager
            collections = self.storage_manager.list_collections()

            # Convert to counts format
            counts = {collection.name: collection.count for collection in collections}

            response_body = {"counts": counts}

            return Response(
                status_code=200,
                content_type="application/json",
                body=json_dumps(response_body),
            )

        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=500,
                content_type="application/json",
                body=json_dumps({"error": "Internal server error"}),
            )
