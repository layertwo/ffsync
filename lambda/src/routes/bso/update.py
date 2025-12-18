import json
from datetime import datetime, timezone
from typing import Any

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (
    CollectionNotFoundException,
    PreconditionFailedException,
    StorageObjectNotFoundException,
    ValidationException,
)
from src.shared.models import BasicStorageObject
from src.shared.utils import json_dumps

logger = Logger()


class UpdateBSORoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.put("/storage/<collectionName>/<objectId>")
        def handle_request(collectionName: str, objectId: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Update a storage object"""
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
            object_id = path_params["objectId"]

            # Parse object from request body
            try:
                body_data = json.loads(body)
                obj_data = body_data["object"]
                storage_object = BasicStorageObject(
                    id=obj_data["id"],
                    payload=obj_data["payload"],
                    sortindex=obj_data.get("sortindex"),
                    ttl=obj_data.get("ttl"),
                    modified=datetime.fromtimestamp(
                        0, tz=timezone.utc
                    ),  # Will be set by DynamoDB service
                )

                # Validate that object ID in body matches path parameter
                if storage_object.id != object_id:
                    raise ValidationException("Object ID in body must match path parameter")

            except (json.JSONDecodeError, KeyError) as e:
                raise ValidationException(f"Invalid request body: {e}")

            # Handle conditional update header
            if_unmodified_since = None
            if_unmodified_since_header = event.headers.get("x-if-unmodified-since")
            if if_unmodified_since_header:
                try:
                    if_unmodified_since = int(if_unmodified_since_header)  # noqa: F841
                except ValueError:
                    raise ValidationException("Invalid X-If-Unmodified-Since header")

            # Update storage object using storage manager with user_id
            updated_object = self.storage_manager.update_storage_object(
                user_id,
                collection_name,
                object_id,
                payload=storage_object.payload,
                sortindex=storage_object.sortindex,
                ttl=storage_object.ttl,
            )

            # Convert to dict using dataclass serialization
            obj_dict = updated_object.to_dict()

            # Remove None values
            if obj_dict.get("sortindex") is None:
                del obj_dict["sortindex"]
            if obj_dict.get("ttl") is None:
                del obj_dict["ttl"]

            response_body: dict[str, Any] = {
                "object": obj_dict,
                "modified": obj_dict["modified"],
            }

            return Response(
                status_code=200,
                content_type="application/json",
                body=json_dumps(response_body),
            )

        except ValidationException as e:
            return Response(
                status_code=400,
                content_type="application/json",
                body=json_dumps({"error": str(e)}),
            )
        except CollectionNotFoundException as e:
            return Response(
                status_code=404,
                content_type="application/json",
                body=json_dumps({"error": str(e)}),
            )
        except StorageObjectNotFoundException as e:
            return Response(
                status_code=404,
                content_type="application/json",
                body=json_dumps({"error": str(e)}),
            )
        except PreconditionFailedException as e:
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
