from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import ValidationException
from src.shared.models import ValidationError, validate_collection_name
from src.shared.utils import json_dumps

logger = Logger()


class ReadCollectionRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/1.5/<uid>/storage/<collectionName>")
        def handle_request(uid: str, collectionName: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Get collection metadata or retrieve objects with filtering"""
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
            query_params = event.query_string_parameters or {}
            headers = event.headers or {}
            collection_name = path_params["collectionName"]

            # Validate collection name before any storage call
            try:
                validate_collection_name(collection_name)
            except ValidationError as e:
                raise ValidationException(str(e))

            # Check for conditional GET headers (Requirement 6.1, 6.2)
            if_modified_since = headers.get("x-if-modified-since")
            if_unmodified_since = headers.get("x-if-unmodified-since")

            # Both headers cannot be present at the same time (Requirement 6.3)
            if if_modified_since and if_unmodified_since:
                return Response(
                    status_code=400,
                    content_type="application/json",
                    body=json_dumps(
                        {
                            "error": "Cannot specify both X-If-Modified-Since and X-If-Unmodified-Since"
                        }
                    ),
                )

            # Validate X-If-Modified-Since header (Requirement 6.4)
            if if_modified_since:
                try:
                    if_modified_since_ts = float(if_modified_since)
                    if if_modified_since_ts < 0:
                        raise ValueError("Timestamp must be positive")
                except (ValueError, TypeError):
                    return Response(
                        status_code=400,
                        content_type="application/json",
                        body=json_dumps(
                            {"error": "X-If-Modified-Since must be a valid positive decimal"}
                        ),
                    )

            # Return objects from collection with filtering
            # Per Mozilla spec (Requirement 2.2), return empty list for non-existent collections
            objects = self.storage_manager.get_collection_objects(
                user_id,
                collection_name,
                ids=query_params.get("ids"),
                newer=self._parse_timestamp(query_params.get("newer")),
                older=self._parse_timestamp(query_params.get("older")),
                sort=query_params.get("sort", "newest"),
                limit=self._parse_int(query_params.get("limit"), 100),
                offset=self._parse_int(query_params.get("offset"), 0),
                full=self._parse_bool(query_params.get("full", "1")),
            )

            # Get last modified timestamp
            last_modified = objects.get("last_modified")
            if isinstance(last_modified, float):
                last_modified_ts = last_modified
            elif last_modified is not None and hasattr(last_modified, "timestamp"):
                last_modified_ts = last_modified.timestamp()
            else:
                last_modified_ts = 0.0

            # Check conditional GET (Requirement 6.1, 6.2)
            if if_modified_since:
                if last_modified_ts <= if_modified_since_ts:
                    # Resource has not been modified, return 304
                    return Response(
                        status_code=304,
                        content_type="application/json",
                        body="",
                        headers={"X-Last-Modified": str(last_modified_ts)},
                    )

            # Determine response format based on 'full' parameter
            full = self._parse_bool(query_params.get("full", "0"))

            if full:
                # Return full BSO objects (without TTL field per Requirement 11.4)
                response_body = [self._format_object(obj) for obj in objects.get("items", [])]
            else:
                # Return just BSO IDs
                response_body = [obj.id for obj in objects.get("items", [])]

            response_headers = {"X-Last-Modified": str(last_modified_ts)}

            # Add X-Weave-Records header indicating total number of records (Requirement 2.14)
            response_headers["X-Weave-Records"] = str(len(response_body))

            # Add X-Weave-Next-Offset header if more results available
            if objects.get("next_offset") is not None:
                response_headers["X-Weave-Next-Offset"] = str(objects["next_offset"])

            # Always return application/json (API Gateway handles Accept header validation)
            return Response(
                status_code=200,
                content_type="application/json",
                body=json_dumps(response_body),
                headers=response_headers,
            )

        except ValidationException as e:
            return Response(
                status_code=400,
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

    def _parse_timestamp(self, value):
        """Parse timestamp from string"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):  # pragma: nocover
            return None

    def _parse_int(self, value, default):
        """Parse integer with default"""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):  # pragma: nocover
            return default

    def _parse_bool(self, value):
        """Parse boolean from string"""
        if value is None:
            return True  # pragma: nocover
        return value.lower() in ("1", "true", "yes")

    def _format_object(self, obj):
        """Format storage object for response"""
        # Convert to dict using dataclass serialization
        obj_dict = obj.to_dict()

        # Remove None values
        if obj_dict.get("sortindex") is None:
            del obj_dict["sortindex"]
        if obj_dict.get("ttl") is None:
            del obj_dict["ttl"]

        return obj_dict
