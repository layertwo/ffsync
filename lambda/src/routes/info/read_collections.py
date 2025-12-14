from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.utils import json_dumps

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
            collections_map = {collection.name: collection.to_dict() for collection in collections}

            response_body = {"collections": collections_map}

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
