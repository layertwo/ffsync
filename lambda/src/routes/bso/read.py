import json

from aws_lambda_powertools import Logger
from aws_lambda_proxy import Response, StatusCode

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

    def bind(self, api):
        @api.get("/storage/{collectionName}/{objectId}")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Get a specific storage object"""
        try:
            collection_name = event["pathParameters"]["collectionName"]
            object_id = event["pathParameters"]["objectId"]

            # Get storage object using storage manager
            storage_object = self.storage_manager.get_storage_object(
                collection_name, object_id
            )

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
                status_code=StatusCode.OK,
                content_type="application/json",
                body=json.dumps(response_body),
                headers={"X-Last-Modified": str(storage_object.modified)},
            )

        except ValidationException as e:
            return Response(
                status_code=StatusCode.BAD_REQUEST,
                content_type="application/json",
                body=json.dumps({"error": str(e)}),
            )
        except CollectionNotFoundException as e:
            return Response(
                status_code=StatusCode.NOT_FOUND,
                content_type="application/json",
                body=json.dumps({"error": str(e)}),
            )
        except StorageObjectNotFoundException as e:
            return Response(
                status_code=StatusCode.NOT_FOUND,
                content_type="application/json",
                body=json.dumps({"error": str(e)}),
            )
        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=StatusCode.INTERNAL_SERVER_ERROR,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )
