from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import CollectionNotFoundException, ValidationException
from src.shared.utils import json_dumps

logger = Logger()


class DeleteCollectionRoute(BaseRoute):
    def __init__(self, dynamodb_service: StorageManager):
        self.dynamodb_service = dynamodb_service

    def bind(self, app: APIGatewayRestResolver):
        @app.delete("/storage/<collectionName>")
        def handle_request(collectionName: str):
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Delete an entire collection"""
        try:
            path_params = event.path_parameters or {}
            collection_name = path_params["collectionName"]

            # Delete collection using DynamoDB service
            modified_timestamp = self.dynamodb_service.delete_collection(collection_name)

            response_body = {"modified": modified_timestamp}

            return Response(
                status_code=200,
                content_type="application/json",
                body=json_dumps(response_body),
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
