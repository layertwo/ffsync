import json

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.models import CollectionsResponse

logger = Logger()


class ListCollectionsRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/1.5/<uid>/storage")
        def handle_request(uid: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """List all collections with their metadata"""
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

            response = CollectionsResponse(collections=collections)

            return Response(
                status_code=200,
                content_type="application/json",
                body=response.model_dump_json(),
            )

        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=500,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )
