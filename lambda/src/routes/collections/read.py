from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import CollectionNotFoundException, ValidationException
from src.shared.utils import json_dumps

logger = Logger()


class ReadCollectionRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/storage/<collectionName>")
        def handle_request(collectionName: str):
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
            collection_name = path_params["collectionName"]

            # Check if this is a request for objects or just metadata
            has_object_filters = any(
                param in query_params
                for param in [
                    "ids",
                    "newer",
                    "older",
                    "sort",
                    "limit",
                    "offset",
                    "full",
                ]
            )

            if has_object_filters:
                # Return objects from collection with filtering
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

                response_body = {
                    "objects": [self._format_object(obj) for obj in objects.get("items", [])],
                    "more": objects.get("more", False),
                }

                if objects.get("next_offset"):
                    response_body["next_offset"] = objects["next_offset"]

                return Response(
                    status_code=200,
                    content_type="application/json",
                    body=json_dumps(response_body),
                    headers={"X-Last-Modified": str(objects.get("last_modified", 0))},
                )
            else:
                # Return collection metadata only
                collection_data = self.storage_manager.get_collection(user_id, collection_name)

                # Convert to dict using dataclass serialization
                collection_dict = collection_data.to_dict()

                response_body = {"collection": collection_dict}

                return Response(
                    status_code=200,
                    content_type="application/json",
                    body=json_dumps(response_body),
                    headers={"X-Last-Modified": str(collection_dict["modified"])},
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
