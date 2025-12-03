import json

from aws_lambda_proxy import Response, StatusCode
from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute


class ReadCollectionsInfoRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, api):
        @api.get("/info/collections")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Get metadata for all collections"""
        try:
            # Get collections using storage manager
            collections = self.storage_manager.list_collections()

            # Convert to map format as expected by the Smithy model
            collections_map = {
                collection.name: {
                    "name": collection.name,
                    "modified": collection.modified,
                    "count": collection.count,
                    "usage": collection.usage,
                }
                for collection in collections
            }

            response_body = {"collections": collections_map}

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
