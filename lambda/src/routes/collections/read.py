import json

from aws_lambda_powertools import Logger
from aws_lambda_proxy import Response, StatusCode

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import CollectionNotFoundException, ValidationException

logger = Logger()


class ReadCollectionRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, api):
        @api.get("/storage/{collectionName}")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Get collection metadata or retrieve objects with filtering"""
        try:
            collection_name = event["pathParameters"]["collectionName"]
            query_params = event.get("queryStringParameters") or {}

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
                    "objects": [
                        self._format_object(obj) for obj in objects.get("items", [])
                    ],
                    "more": objects.get("more", False),
                }

                if objects.get("next_offset"):
                    response_body["next_offset"] = objects["next_offset"]

                return Response(
                    status_code=StatusCode.OK,
                    content_type="application/json",
                    body=json.dumps(response_body),
                    headers={"X-Last-Modified": str(objects.get("last_modified", 0))},
                )
            else:
                # Return collection metadata only
                collection_data = self.storage_manager.get_collection(collection_name)

                response_body = {
                    "collection": {
                        "name": collection_data.name,
                        "modified": collection_data.modified,
                        "count": collection_data.count,
                        "usage": collection_data.usage,
                    }
                }

                return Response(
                    status_code=StatusCode.OK,
                    content_type="application/json",
                    body=json.dumps(response_body),
                    headers={"X-Last-Modified": str(collection_data.modified)},
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
        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=StatusCode.INTERNAL_SERVER_ERROR,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
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
        result = {
            "id": obj.id,
            "payload": obj.payload,
            "modified": obj.modified,
        }
        if obj.sortindex is not None:
            result["sortindex"] = obj.sortindex
        if obj.ttl is not None:
            result["ttl"] = obj.ttl
        return result
