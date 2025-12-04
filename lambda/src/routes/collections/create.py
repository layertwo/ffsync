import json

from aws_lambda_powertools import Logger
from aws_lambda_proxy import API, Response, StatusCode

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (
    ConflictException,
    PreconditionFailedException,
    ValidationException,
)
from src.shared.models import BasicStorageObject

logger = Logger()


class CreateCollectionRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, api: API):
        @api.post("/storage/{collectionName}")
        @api.pass_event
        def handle_with_event(event: dict) -> Response:
            return self.handle(event)

    def handle(self, event: dict) -> Response:
        """Create a new collection or batch create/update objects"""
        try:
            collection_name = event["pathParameters"]["collectionName"]
            headers = event.get("headers", {})

            # Check conditional headers
            if_unmodified_since = headers.get("X-If-Unmodified-Since")
            if if_unmodified_since and not self._check_precondition(
                collection_name, if_unmodified_since
            ):
                return Response(
                    status_code=StatusCode.PRECONDITION_FAILED,
                    content_type="application/json",
                    body=json.dumps({"error": "Precondition failed"}),
                )

            # Parse objects from request body - support both direct array and wrapped object
            objects = []
            if event.get("body"):
                try:
                    body_data = json.loads(event["body"])

                    # Handle direct array of objects (Mozilla API format)
                    if isinstance(body_data, list):
                        objects_data = body_data
                    # Handle wrapped objects
                    elif "objects" in body_data:
                        objects_data = body_data["objects"]
                    else:  # pragma: nocover
                        objects_data = []

                    objects = [
                        BasicStorageObject(
                            id=obj["id"],
                            payload=obj["payload"],
                            sortindex=obj.get("sortindex"),
                            ttl=obj.get("ttl"),
                            modified=0,  # Will be set by storage manager
                        )
                        for obj in objects_data
                    ]
                except (json.JSONDecodeError, KeyError) as e:
                    raise ValidationException(f"Invalid request body: {e}")

            # Create/update collection using storage manager
            collection_data, batch_result = self.storage_manager.create_or_update_collection(
                collection_name, objects if objects else None
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
                status_code=StatusCode.CREATED,
                content_type="application/json",
                body=json.dumps(response_body),
            )

        except ValidationException as e:
            return Response(
                status_code=StatusCode.BAD_REQUEST,
                content_type="application/json",
                body=json.dumps({"error": str(e)}),
            )
        except ConflictException as e:
            return Response(
                status_code=StatusCode.CONFLICT,
                content_type="application/json",
                body=json.dumps({"error": str(e)}),
            )
        except PreconditionFailedException as e:  # pragma: nocover
            return Response(
                status_code=StatusCode.PRECONDITION_FAILED,
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

    def _check_precondition(self, collection_name, if_unmodified_since):
        """Check if collection was modified since given timestamp"""
        try:
            timestamp = float(if_unmodified_since)
            collection = self.storage_manager.get_collection(collection_name)
            return collection.modified <= timestamp
        except (ValueError, Exception):  # pragma: nocover
            return True  # If we can't check, allow the operation
