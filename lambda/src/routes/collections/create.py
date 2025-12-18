import json
from datetime import datetime, timezone

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (
    ConflictException,
    PreconditionFailedException,
    ValidationException,
)
from src.shared.models import BasicStorageObject
from src.shared.utils import json_dumps

logger = Logger()


class CreateCollectionRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/storage/<collectionName>")
        def handle_request(collectionName: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Create a new collection or batch create/update objects"""
        try:
            # Extract user_id from authorizer context
            user_id = event.get("requestContext", {}).get("authorizer", {}).get("user_id")
            if not user_id:
                return Response(
                    status_code=401,
                    content_type="application/json",
                    body=json_dumps({"error": "Unauthorized"}),
                )

            path_params = event.path_parameters or {}
            body = event.body
            collection_name = path_params["collectionName"]

            # Check conditional headers
            if_unmodified_since = event.headers.get("x-if-unmodified-since")
            if if_unmodified_since and not self._check_precondition(
                user_id, collection_name, if_unmodified_since
            ):
                return Response(
                    status_code=412,
                    content_type="application/json",
                    body=json_dumps({"error": "Precondition failed"}),
                )

            # Parse objects from request body - support both direct array and wrapped object
            objects = []
            if body:
                try:
                    body_data = json.loads(body)

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
                            modified=datetime.fromtimestamp(
                                0, tz=timezone.utc
                            ),  # Will be set by storage manager
                        )
                        for obj in objects_data
                    ]
                except (json.JSONDecodeError, KeyError) as e:
                    raise ValidationException(f"Invalid request body: {e}")

            # Create/update collection using storage manager
            collection_data, batch_result = self.storage_manager.create_or_update_collection(
                user_id, collection_name, objects if objects else None
            )

            # Convert to dict using dataclass serialization
            collection_dict = collection_data.to_dict()
            batch_dict = batch_result.to_dict()

            response_body = {
                "collection": collection_dict,
                "batchResult": batch_dict,
            }

            return Response(
                status_code=201,
                content_type="application/json",
                body=json_dumps(response_body),
            )

        except ValidationException as e:
            return Response(
                status_code=400,
                content_type="application/json",
                body=json_dumps({"error": str(e)}),
            )
        except ConflictException as e:
            return Response(
                status_code=409,
                content_type="application/json",
                body=json_dumps({"error": str(e)}),
            )
        except PreconditionFailedException as e:  # pragma: nocover
            return Response(
                status_code=412,
                content_type="application/json",
                body=json_dumps({"error": str(e)}),
            )
        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=500,
                content_type="application/json",
                body=json_dumps({"error": "Internal server error"}),
            )

    def _check_precondition(self, user_id, collection_name, if_unmodified_since):
        """Check if collection was modified since given timestamp"""
        try:
            timestamp = float(if_unmodified_since)
            collection = self.storage_manager.get_collection(user_id, collection_name)
            return collection.modified <= datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (ValueError, Exception):  # pragma: nocover
            return True  # If we can't check, allow the operation
