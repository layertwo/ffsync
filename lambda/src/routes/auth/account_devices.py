"""AccountDevices route — GET /v1/account/devices"""

import json
from typing import Sequence

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler

from src.services.device_manager import DeviceManager
from src.shared.base_route import BaseRoute


class AccountDevicesRoute(BaseRoute):
    """List all devices for the authenticated user."""

    def __init__(
        self,
        device_manager: DeviceManager,
        middlewares: Sequence[BaseMiddlewareHandler] = (),
    ):
        self._device_manager = device_manager
        self.middlewares = middlewares

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/v1/account/devices", middlewares=list(self.middlewares))
        def handle_account_devices():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        uid = event["requestContext"]["hawk_uid"]
        session_token_id = event["requestContext"].get("hawk_token_id", "")

        params = event.query_string_parameters or {}
        filter_ts = params.get("filterIdleDevicesTimestamp")
        filter_idle = int(filter_ts) if filter_ts else None

        devices = self._device_manager.get_devices(uid, filter_idle)
        for d in devices:
            d["isCurrentDevice"] = d.get("sessionTokenId") == session_token_id

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps(devices),
        )
