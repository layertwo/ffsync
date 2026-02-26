from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import CollectionNotFoundException, ValidationException
from src.shared.models import ValidationError, validate_collection_name
from src.shared.utils import json_dumps

logger = Logger()


class DeleteCollectionRoute(BaseRoute):
    def __init__(self, dynamodb_service: StorageManager):
        self.dynamodb_service = dynamodb_service

    def bind(self, app: APIGatewayRestResolver):
        @app.delete("/1.5/<uid>/storage/<collectionName>")
        def handle_request(uid: str, collectionName: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Delete an entire collection or specific BSOs"""
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
            try:
                validate_collection_name(collection_name)
            except ValidationError as e:
                raise ValidationException(str(e))

            # Check if selective deletion (ids parameter present)
            ids_param = query_params.get("ids")

            if ids_param:
                # Selective deletion - delete only specified BSOs (Requirement 4.1, 4.2, 4.5)
                ids = [id.strip() for id in ids_param.split(",")]
                modified_timestamp = self.dynamodb_service.delete_collection_objects(
                    user_id, collection_name, ids
                )
            else:
                # Delete entire collection (Requirement 4.3, 4.4)
                modified_timestamp = self.dynamodb_service.delete_collection(
                    user_id, collection_name
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
        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=500,
                content_type="application/json",
                body=json_dumps({"error": "Internal server error"}),
            )
