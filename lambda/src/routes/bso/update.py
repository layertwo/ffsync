import json

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (
    CollectionNotFoundException,
    PreconditionFailedException,
    RequestTooLargeException,
    StorageObjectNotFoundException,
    ValidationException,
)
from src.shared.models import (
    ValidationError,
    validate_bso_id,
    validate_collection_name,
    validate_payload_size,
    validate_sortindex,
    validate_ttl,
)
from src.shared.utils import json_dumps

logger = Logger()


class UpdateBSORoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.put("/1.5/<uid>/storage/<collectionName>/<objectId>")
        def handle_request(uid: str, collectionName: str, objectId: str):
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
            try:
                validate_collection_name(collection_name)
            except ValidationError as e:
                raise ValidationException(str(e))

            # Parse BSO fields directly from request body (per SyncStorage API v1.5 spec)
            try:
                obj_data = json.loads(body)
            except (json.JSONDecodeError, TypeError) as e:
                raise ValidationException(f"Invalid request body: {e}")

            if not isinstance(obj_data, dict):
                raise ValidationException("Invalid request body: expected JSON object")

            # Validate BSO ID from path parameter (Requirements 10.2, 10.3)
            try:
                validate_bso_id(object_id)
            except ValidationError as e:
                raise ValidationException(str(e))

            # If body contains id, validate it matches the path parameter
            if "id" in obj_data and obj_data["id"] != object_id:
                raise ValidationException("Object ID in body must match path parameter")

            # Validate payload size if provided (Requirement 10.1)
            payload = obj_data.get("payload")
            if payload is not None:
                try:
                    validate_payload_size(payload)
                except ValidationError as e:
                    raise RequestTooLargeException(str(e))

            # Validate sortindex if provided
            sortindex = obj_data.get("sortindex")
            try:
                validate_sortindex(sortindex)
            except ValidationError as e:
                raise ValidationException(str(e))

            # Validate TTL if provided
            ttl = obj_data.get("ttl")
            try:
                validate_ttl(ttl)
            except ValidationError as e:
                raise ValidationException(str(e))

            # Handle conditional update header (Requirements 5.1-5.3)
            if_unmodified_since = None
            if_unmodified_since_header = event.headers.get("x-if-unmodified-since")
            if if_unmodified_since_header:
                try:
                    if_unmodified_since = float(if_unmodified_since_header)
                except ValueError:
                    raise ValidationException("Invalid X-If-Unmodified-Since header")

            # Update storage object using storage manager with user_id
            updated_object = self.storage_manager.update_storage_object(
                user_id,
                collection_name,
                object_id,
                if_unmodified_since=if_unmodified_since,
                payload=payload,
                sortindex=sortindex,
                ttl=ttl,
            )

            # Per SyncStorage API v1.5 spec, PUT returns the new
            # last-modified time for the collection as a plain number
            modified = updated_object.modified.timestamp()

            return Response(
                status_code=200,
                content_type="application/json",
                body=json_dumps(modified),
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
        except RequestTooLargeException as e:
            return Response(
                status_code=413,
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
