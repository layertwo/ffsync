import json

from aws_lambda_powertools import Logger
from aws_lambda_proxy import Response, StatusCode

from src.shared.base_route import BaseRoute
from src.shared.models import get_current_timestamp

logger = Logger()


class DeleteAllStorageRoute(BaseRoute):

    def bind(self, api):
        @api.delete("/storage")
        @api.pass_event
        def handle_with_event(event):
            return self.handle(event)

    def handle(self, event):
        """Delete all storage data for the authenticated user"""
        try:
            # TODO: Implement authentication validation
            # TODO: Implement deletion of all collections for authenticated user

            # For now, return a placeholder response
            timestamp = get_current_timestamp()

            return Response(
                status_code=StatusCode.OK,
                content_type="application/json",
                body=json.dumps({"modified": timestamp}),
            )

        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=StatusCode.INTERNAL_SERVER_ERROR,
                content_type="application/json",
                body=json.dumps({"error": "Internal server error"}),
            )
