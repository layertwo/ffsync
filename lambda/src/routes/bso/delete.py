import json
from typing import Any

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (
    CollectionNotFoundException,
    StorageObjectNotFoundException,
    ValidationException,
)
from src.shared.models import (
    ModifiedOutput,
    ValidationError,
    validate_bso_id,
    validate_collection_name,
)

logger = Logger()


class DeleteBSORoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver) -> None:
        @app.delete("/1.5/<uid>/storage/<collectionName>/<objectId>")
        def handle_request(uid: str, collectionName: str, objectId: str) -> Response[Any]:
            return self.handle(app.current_event)

    def handle(self, event: APIGatewayProxyEvent) -> Response:
        """Delete a specific storage object"""
        try:
            user_id = self.hawk_uid(event)
            if not user_id:
                return self.unauthorized()

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

            result = ModifiedOutput(modified=modified_timestamp)

            return Response(
                status_code=200,
                content_type="application/json",
                body=result.model_dump_json(),
                headers={"X-Last-Modified": str(round(modified_timestamp, 2))},
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
        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=500,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )
