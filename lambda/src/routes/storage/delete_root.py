from typing import Any

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.models import ModifiedOutput


class DeleteAllRootRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver) -> None:
        @app.delete("/1.5/<uid>")
        def handle_request(uid: str) -> Response[Any]:
            return self.handle(app.current_event)

    def handle(self, event: APIGatewayProxyEvent) -> Response:
        """Delete all storage data for the authenticated user (root endpoint alias)"""
        user_id = self.hawk_uid(event)
        if not user_id:
            return self.unauthorized()

        # Delete all collections and BSOs for the authenticated user
        modified_timestamp = self.storage_manager.delete_all_storage(user_id)

        result = ModifiedOutput(modified=modified_timestamp)
        return Response(
            status_code=200,
            content_type="application/json",
            body=result.model_dump_json(),
            headers={"X-Last-Modified": str(round(modified_timestamp, 2))},
        )
