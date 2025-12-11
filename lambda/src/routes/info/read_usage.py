import json

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute

logger = Logger()


class ReadCollectionUsageRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/info/collection_usage")
        def handle_request():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Get usage information for all collections"""
        try:
            # Get collections using storage manager
            collections = self.storage_manager.list_collections()

            # Convert to usage format
            usage = {collection.name: collection.usage for collection in collections}

            response_body = {"usage": usage}

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
