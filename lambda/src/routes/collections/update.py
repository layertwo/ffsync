import json

from aws_lambda_powertools import Logger
from aws_lambda_proxy import Response, StatusCode

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (CollectionNotFoundException,
                                   PreconditionFailedException,
                                   ValidationException)
from src.shared.models import BasicStorageObject

logger = Logger()


class UpdateCollectionRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, api):
        @api.put("/storage/{collectionName}")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Update collection with batch objects"""
        try:
            collection_name = event["pathParameters"]["collectionName"]

            # Parse objects from request body
            try:
                body_data = json.loads(event["body"])
                objects = [
                    BasicStorageObject(
                        id=obj["id"],
                        payload=obj["payload"],
                        sortindex=obj.get("sortindex"),
                        ttl=obj.get("ttl"),
                        modified=0,  # Will be set by DynamoDB service
                    )
                    for obj in body_data["objects"]
                ]
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

            # Update collection using storage manager
            collection_data, batch_result = self.storage_manager.update_collection(
                collection_name, objects, if_unmodified_since
            )

            response_body = {
                "collection": {
                    "name": collection_data.name,
                    "modified": collection_data.modified,
                    "count": collection_data.count,
                    "usage": collection_data.usage,
                },
                "batchResult": {
                    "success": batch_result.success,
                    "failed": batch_result.failed,
                    "modified": batch_result.modified,
                },
            }

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
        except PreconditionFailedException as e:
            return Response(
                status_code=StatusCode.PRECONDITION_FAILED,
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
