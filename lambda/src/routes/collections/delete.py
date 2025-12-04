import json

from aws_lambda_powertools import Logger
from aws_lambda_proxy import Response, StatusCode

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import CollectionNotFoundException, ValidationException

logger = Logger()


class DeleteCollectionRoute(BaseRoute):
    def __init__(self, dynamodb_service: StorageManager):
        self.dynamodb_service = dynamodb_service

    def bind(self, api):
        @api.delete("/storage/{collectionName}")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Delete an entire collection"""
        try:
            collection_name = event["pathParameters"]["collectionName"]

            # Delete collection using DynamoDB service
            modified_timestamp = self.dynamodb_service.delete_collection(
                collection_name
            )

            response_body = {"modified": modified_timestamp}

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
        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=StatusCode.INTERNAL_SERVER_ERROR,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )
