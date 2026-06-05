import json

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.models import ModifiedOutput

logger = Logger()


class DeleteAllRootRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.delete("/1.5/<uid>")
        def handle_request(uid: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Delete all storage data for the authenticated user (root endpoint alias)"""
        try:
            # Extract user_id from authorizer context
            user_id = event.get("requestContext", {}).get("hawk_uid")
            if not user_id:
                return Response(
                    status_code=401,
                    content_type="application/json",
                    body=json.dumps({"error": "Unauthorized"}),
                )

            # Delete all collections and BSOs for the authenticated user
            modified_timestamp = self.storage_manager.delete_all_storage(user_id)

            result = ModifiedOutput(modified=modified_timestamp)
            return Response(
                status_code=200,
                content_type="application/json",
                body=result.model_dump_json(),
                headers={"X-Last-Modified": str(round(modified_timestamp, 2))},
            )

        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=500,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )
