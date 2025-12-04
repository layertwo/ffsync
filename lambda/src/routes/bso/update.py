import json

from aws_lambda_proxy import Response, StatusCode

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (
    CollectionNotFoundException,
    PreconditionFailedException,
    StorageObjectNotFoundException,
    ValidationException,
)
from src.shared.models import BasicStorageObject


class UpdateBSORoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, api):
        @api.put("/storage/{collectionName}/{objectId}")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Update a storage object"""
        try:
            collection_name = event["pathParameters"]["collectionName"]
            object_id = event["pathParameters"]["objectId"]

            # Parse object from request body
            try:
                body_data = json.loads(event["body"])
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
                    raise ValidationException(
                        "Object ID in body must match path parameter"
                    )

            except (json.JSONDecodeError, KeyError) as e:
                raise ValidationException(f"Invalid request body: {e}")

            # Handle conditional update header
            if_unmodified_since = None
            headers = event.get("headers", {})
            if "X-If-Unmodified-Since" in headers:
                try:
                    if_unmodified_since = int(headers["X-If-Unmodified-Since"])
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
                status_code=StatusCode.OK,
                content_type="application/json",
                body=json.dumps(response_body),
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
        except PreconditionFailedException as e:
            return Response(
                status_code=StatusCode.PRECONDITION_FAILED,
                content_type="application/json",
                body=json.dumps({"error": str(e)}),
            )
        except Exception as e:
            return Response(
                status_code=StatusCode.INTERNAL_SERVER_ERROR,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )
