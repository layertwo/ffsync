import json

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
                    modified=0,  # Will be set by DynamoDB service
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
                    if_unmodified_since = int(if_unmodified_since_header)
                except ValueError:
                    raise ValidationException("Invalid X-If-Unmodified-Since header")

            # Update storage object using storage manager
            updated_object = self.storage_manager.update_storage_object(
                collection_name, object_id, storage_object, if_unmodified_since
            )

            response_body = {
                "object": {
                    "id": updated_object.id,
                    "payload": updated_object.payload,
                    "modified": updated_object.modified,
                    "sortindex": updated_object.sortindex,
                    "ttl": updated_object.ttl,
                },
                "modified": updated_object.modified,
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
