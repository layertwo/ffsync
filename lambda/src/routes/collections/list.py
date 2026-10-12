from typing import Any

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.services.storage_manager import StorageManager
from src.shared.base_route import BaseRoute
from src.shared.models import CollectionsResponse, get_current_timestamp


class ListCollectionsRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, app: APIGatewayRestResolver) -> None:
        @app.get("/1.5/<uid>/storage")
        def handle_request(uid: str) -> Response[Any]:
            return self.handle(app.current_event)

    def handle(self, event: APIGatewayProxyEvent) -> Response:
        """List all collections with their metadata"""
        user_id = self.hawk_uid(event)
        if not user_id:
            return self.unauthorized()

        # Get collections using storage manager
        collections = self.storage_manager.list_collections(user_id)

        response = CollectionsResponse(collections=collections)

        # The target resource is the collection list, so its last-modified time is the
        # newest member's -- or the clock when there is nothing to report.
        last_modified = max((c.modified for c in collections), default=get_current_timestamp())

        return Response(
            status_code=200,
            content_type="application/json",
            body=response.model_dump_json(),
            headers={"X-Last-Modified": f"{last_modified:.2f}"},
        )
