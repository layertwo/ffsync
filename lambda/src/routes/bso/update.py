import json

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from pydantic import ValidationError as PydanticValidationError

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
    BSOInput,
    ValidationError,
    validate_bso_id,
    validate_collection_name,
    validate_payload_size,
)

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
            user_id = event.get("requestContext", {}).get("hawk_uid")
            if not user_id:
                return Response(
                    status_code=401,
                    content_type="application/json",
                    body=json.dumps({"error": "Unauthorized"}),
                )

            path_params = event.path_parameters or {}
            body = event.body
            collection_name = path_params["collectionName"]
            object_id = path_params["objectId"]
            try:
                validate_collection_name(collection_name)
            except ValidationError as e:
                raise ValidationException(str(e))

            # Validate BSO ID from path parameter (Requirements 10.2, 10.3)
            try:
                validate_bso_id(object_id)
            except ValidationError as e:
                raise ValidationException(str(e))

            # Parse and validate BSO fields via Pydantic model
            try:
                bso_input = BSOInput.model_validate_json(body)
            except PydanticValidationError as e:
                raise ValidationException(f"Invalid request body: {e}")
            except (TypeError, ValueError) as e:  # pragma: nocover
                raise ValidationException(f"Invalid request body: {e}")

            # If body contains id, validate it matches the path parameter
            if bso_input.id is not None and bso_input.id != object_id:
                raise ValidationException("Object ID in body must match path parameter")

            # Validate payload byte-size for 413 (Requirement 10.1)
            payload = bso_input.payload
            if payload is not None:
                try:
                    validate_payload_size(payload)
                except ValidationError as e:
                    raise RequestTooLargeException(str(e))

            sortindex = bso_input.sortindex
            ttl = bso_input.ttl

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
            modified = updated_object.modified

            return Response(
                status_code=200,
                content_type="application/json",
                body=json.dumps(modified),
                headers={"X-Last-Modified": str(round(modified, 2))},
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
        except RequestTooLargeException as e:
            return Response(
                status_code=413,
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
