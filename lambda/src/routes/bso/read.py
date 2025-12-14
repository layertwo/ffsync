from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (
    CollectionNotFoundException,
    StorageObjectNotFoundException,
    ValidationException,
)
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
            path_params = event.path_parameters or {}
            collection_name = path_params["collectionName"]
            object_id = path_params["objectId"]

            # Get storage object using storage manager
            storage_object = self.storage_manager.get_storage_object(collection_name, object_id)

            # Convert to dict using dataclass serialization
            obj_dict = storage_object.to_dict()

            # Remove None values
            if obj_dict.get("sortindex") is None:
                del obj_dict["sortindex"]
            if obj_dict.get("ttl") is None:
                del obj_dict["ttl"]

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
