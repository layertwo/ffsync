import json

from aws_lambda_powertools import Logger
from aws_lambda_proxy import API, Response, StatusCode

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute

logger = Logger()


class ReadCollectionUsageRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, api: API):
        @api.get("/info/collection_usage")
        @api.pass_event
        def handle_with_event(event: dict) -> Response:
            return self.handle(event)

    def handle(self, event: dict) -> Response:
        """Get usage information for all collections"""
        try:
            # Get collections using storage manager
            collections = self.storage_manager.list_collections()

            # Convert to usage format
            usage = {collection.name: collection.usage for collection in collections}

            response_body = {"usage": usage}

            return Response(
                status_code=StatusCode.OK,
                content_type="application/json",
                body=json.dumps(response_body),
            )

        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=StatusCode.INTERNAL_SERVER_ERROR,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )
