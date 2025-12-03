import json

from aws_lambda_proxy import Response, StatusCode
from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute


class ReadQuotaInfoRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, api):
        @api.get("/info/quota")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
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
                status_code=StatusCode.OK,
                content_type="application/json",
                body=json.dumps(response_body),
            )

        except Exception as e:
            return Response(
                status_code=StatusCode.INTERNAL_SERVER_ERROR,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )
