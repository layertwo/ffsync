import json

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute

logger = Logger()

# Default quota limit in KB (None means unlimited/not enforced)
DEFAULT_QUOTA_KB = None


class ReadQuotaInfoRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager, quota_kb: int | None = DEFAULT_QUOTA_KB):
        self.storage_manager = storage_manager
        self.quota_kb = quota_kb

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/1.5/<uid>/info/quota")
        def handle_request(uid: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """
        Get quota information for the authenticated user.

        Returns Mozilla format: [usage_kb, quota_kb or null]
        - usage_kb: Current storage usage in KB
        - quota_kb: Storage quota in KB, or null if not enforced
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

            # Get collections using storage manager to calculate current usage
            collections = self.storage_manager.list_collections(user_id)

            # Calculate total usage in bytes, then convert to KB
            total_usage_bytes = sum(collection.usage for collection in collections)
            usage_kb = total_usage_bytes / 1024

            # Return Mozilla format: [usage_kb, quota_kb or null]
            response_body = [usage_kb, self.quota_kb]

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
