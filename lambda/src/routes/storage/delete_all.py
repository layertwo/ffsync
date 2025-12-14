from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.shared.base_route import BaseRoute
from src.shared.models import get_current_timestamp
from src.shared.utils import json_dumps

logger = Logger()


class DeleteAllStorageRoute(BaseRoute):

    def bind(self, app: APIGatewayRestResolver):
        @app.delete("/storage")
        def handle_request():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Delete all storage data for the authenticated user"""
        try:
            # TODO: Implement authentication validation
            # TODO: Implement deletion of all collections for authenticated user

            # For now, return a placeholder response
            timestamp = get_current_timestamp()

            return Response(
                status_code=200,
                content_type="application/json",
                body=json_dumps({"modified": timestamp}),
            )

        except Exception as e:
            logger.error(f"Internal server error: {e}")
            return Response(
                status_code=500,
                content_type="application/json",
                body=json_dumps({"error": "Internal server error"}),
            )
