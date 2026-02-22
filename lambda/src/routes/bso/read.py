from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (
    CollectionNotFoundException,
    StorageObjectNotFoundException,
    ValidationException,
)
from src.shared.models import ValidationError, validate_bso_id, validate_collection_name
from src.shared.utils import json_dumps

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
            # Extract user_id from authorizer context
            user_id = event.get("requestContext", {}).get("authorizer", {}).get("user_id")
            if not user_id:
                return Response(
                    status_code=401,
                    content_type="application/json",
                    body=json_dumps({"error": "Unauthorized"}),
                )

            path_params = event.path_parameters or {}
            collection_name = path_params["collectionName"]
            object_id = path_params["objectId"]
            try:
                validate_collection_name(collection_name)
                validate_bso_id(object_id)
            except ValidationError as e:
                raise ValidationException(str(e))

            # Handle conditional GET headers (Requirements 6.1-6.4)
            headers = event.get("headers", {})
            if_modified_since_header = headers.get("x-if-modified-since")
            if_unmodified_since_header = headers.get("x-if-unmodified-since")

            # Requirement 6.3: Cannot have both headers
            if if_modified_since_header and if_unmodified_since_header:
                return Response(
                    status_code=400,
                    content_type="application/json",
                    body=json_dumps(
                        {
                            "error": "Cannot specify both X-If-Modified-Since and X-If-Unmodified-Since"
                        }
                    ),
                )

            # Parse X-If-Modified-Since if present
            if_modified_since = None
            if if_modified_since_header:
                try:
                    if_modified_since = float(if_modified_since_header)
                    # Requirement 6.4: Must be a valid positive decimal
                    if if_modified_since < 0:
                        raise ValueError("Must be positive")
                except ValueError:
                    return Response(
                        status_code=400,
                        content_type="application/json",
                        body=json_dumps({"error": "Invalid X-If-Modified-Since header"}),
                    )

            # Get storage object using storage manager with user_id
            storage_object = self.storage_manager.get_storage_object(
                user_id, collection_name, object_id
            )

            # Requirement 6.2: Return 304 if not modified since specified timestamp
            if if_modified_since is not None:
                # Convert modified datetime to timestamp for comparison
                modified_timestamp = storage_object.modified.timestamp()
                if modified_timestamp <= if_modified_since:
                    return Response(
                        status_code=304,
                        content_type="application/json",
                        body="",
                        headers={"X-Last-Modified": str(round(modified_timestamp, 2))},
                    )

            # Convert to dict using dataclass serialization
            obj_dict = storage_object.to_dict()

            # TTL is write-only per Mozilla spec - always exclude from response
            if "ttl" in obj_dict:  # pragma: nocover
                del obj_dict["ttl"]

            # Remove None values for optional fields
            if obj_dict.get("sortindex") is None:
                del obj_dict["sortindex"]

            response_body = {"object": obj_dict}

            return Response(
                status_code=200,
                content_type="application/json",
                body=json_dumps(response_body),
                headers={"X-Last-Modified": str(obj_dict["modified"])},
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
        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=500,
                content_type="application/json",
                body=json_dumps({"error": "Internal server error"}),
            )
