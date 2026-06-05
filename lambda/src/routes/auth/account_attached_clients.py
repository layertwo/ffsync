"""AccountAttachedClients route — GET /v1/account/attached_clients"""

from typing import Sequence

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler

from src.services.device_manager import DeviceManager
from src.shared.base_route import BaseRoute
from src.shared.models import AttachedClientOutput, ClientListAdapter


class AccountAttachedClientsRoute(BaseRoute):
    """Return attached clients derived from device records."""

    def __init__(
        self,
        device_manager: DeviceManager,
        middlewares: Sequence[BaseMiddlewareHandler] = (),
    ):
        self._device_manager = device_manager
        self.middlewares = middlewares

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/v1/account/attached_clients", middlewares=list(self.middlewares))
        def handle_account_attached_clients():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        uid = event["requestContext"]["hawk_uid"]
        session_token_id = event["requestContext"].get("hawk_token_id", "")

        devices = self._device_manager.get_devices(uid)
        clients = []
        for d in devices:
            client = AttachedClientOutput(
                device_id=d.get("id"),
                session_token_id=d.get("sessionTokenId"),
                is_current_session=d.get("sessionTokenId") == session_token_id,
                device_type=d.get("type"),
                name=d.get("name"),
                created_time=d.get("createdAt"),
                last_access_time=d.get("lastAccessTime"),
                user_agent="",
            )
            clients.append(client)

        return Response(
            status_code=200,
            content_type="application/json",
            body=ClientListAdapter.dump_json(clients, by_alias=True).decode(),
        )
