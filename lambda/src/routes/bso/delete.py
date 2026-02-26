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


class DeleteBSORoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.delete("/1.5/<uid>/storage/<collectionName>/<objectId>")
        def handle_request(uid: str, collectionName: str, objectId: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Delete a specific storage object"""
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

            # Delete storage object using storage manager with user_id
            modified_timestamp = self.storage_manager.delete_storage_object(
                user_id, collection_name, object_id
            )

            response_body = {"modified": modified_timestamp}

            return Response(
                status_code=200,
                content_type="application/json",
                body=json_dumps(response_body),
                headers={"X-Last-Modified": str(round(modified_timestamp, 2))},
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
