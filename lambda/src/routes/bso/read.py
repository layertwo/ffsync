import json

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (
    CollectionNotFoundException,
    StorageObjectNotFoundException,
    ValidationException,
)

logger = Logger()


class ReadBSORoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/storage/<collectionName>/<objectId>")
        def handle_request(collectionName: str, objectId: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Get a specific storage object"""
        try:
            path_params = event.path_parameters or {}
            collection_name = path_params["collectionName"]
            object_id = path_params["objectId"]

            # Get storage object using storage manager
            storage_object = self.storage_manager.get_storage_object(collection_name, object_id)

            response_body = {
                "object": {
                    "id": storage_object.id,
                    "payload": storage_object.payload,
                    "modified": storage_object.modified,
                    "sortindex": storage_object.sortindex,
                    "ttl": storage_object.ttl,
                }
            }

            # Remove None values
            if response_body["object"]["sortindex"] is None:
                del response_body["object"]["sortindex"]
            if response_body["object"]["ttl"] is None:
                del response_body["object"]["ttl"]

            return Response(
                status_code=200,
                content_type="application/json",
                body=json.dumps(response_body),
                headers={"X-Last-Modified": str(storage_object.modified)},
            )

        except ValidationException as e:
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps({"error": str(e)}),
            )
        except CollectionNotFoundException as e:
            return Response(
                status_code=404,
                content_type="application/json",
                body=json.dumps({"error": str(e)}),
            )
        except StorageObjectNotFoundException as e:
            return Response(
                status_code=404,
                content_type="application/json",
                body=json.dumps({"error": str(e)}),
            )
        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=500,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )
