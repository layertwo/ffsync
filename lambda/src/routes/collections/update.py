import json

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (
    CollectionNotFoundException,
    PreconditionFailedException,
    ValidationException,
)
from src.shared.models import BasicStorageObject

logger = Logger()


class UpdateCollectionRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.put("/storage/<collectionName>")
        def handle_request(collectionName: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Update collection with batch objects"""
        try:
            path_params = event.path_parameters or {}
            body = event.body
            collection_name = path_params["collectionName"]

            # Parse objects from request body
            try:
                body_data = json.loads(body)
                objects = [
                    BasicStorageObject(
                        id=obj["id"],
                        payload=obj["payload"],
                        sortindex=obj.get("sortindex"),
                        ttl=obj.get("ttl"),
                        modified=0,  # Will be set by DynamoDB service
                    )
                    for obj in body_data["objects"]
                ]
            except (json.JSONDecodeError, KeyError) as e:
                raise ValidationException(f"Invalid request body: {e}")

            # Handle conditional update header
            if_unmodified_since = None
            if_unmodified_since_header = event.headers.get("x-if-unmodified-since")
            if if_unmodified_since_header:
                try:
                    if_unmodified_since = int(if_unmodified_since_header)
                except ValueError:
                    raise ValidationException("Invalid X-If-Unmodified-Since header")

            # Update collection using storage manager
            collection_data, batch_result = self.storage_manager.update_collection(
                collection_name=collection_name,
                objects=objects,
            )

            response_body = {
                "collection": {
                    "name": collection_data.name,
                    "modified": collection_data.modified,
                    "count": collection_data.count,
                    "usage": collection_data.usage,
                },
                "batchResult": {
                    "success": batch_result.success,
                    "failed": batch_result.failed,
                    "modified": batch_result.modified,
                },
            }

            return Response(
                status_code=200,
                content_type="application/json",
                body=json.dumps(response_body),
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
        except PreconditionFailedException as e:
            return Response(
                status_code=412,
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
