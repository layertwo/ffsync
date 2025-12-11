import json

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute

logger = Logger()


class ReadQuotaInfoRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/info/quota")
        def handle_request():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Get quota information for the authenticated user"""
        try:
            # Get collections using storage manager to calculate current usage
            collections = self.storage_manager.list_collections()

            current_collections = len(collections)
            current_usage = sum(collection.usage for collection in collections)

            # TODO: Make these configurable per user/tier
            max_collections = 100
            max_usage = 10485760  # 10MB

            response_body = {
                "quota": {
                    "max_collections": max_collections,
                    "max_usage": max_usage,
                    "current_collections": current_collections,
                    "current_usage": current_usage,
                }
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
