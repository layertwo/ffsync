import json

from aws_lambda_proxy import Response, StatusCode
from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute


class ListCollectionsRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, api):
        @api.get("/storage")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
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
