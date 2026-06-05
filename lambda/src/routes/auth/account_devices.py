"""AccountDevices route — GET /v1/account/devices"""

from typing import Sequence

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler

from src.services.device_manager import DeviceManager
from src.shared.base_route import BaseRoute
from src.shared.models import DeviceListAdapter, DeviceOutput


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
        results = []
        for d in devices:
            device = DeviceOutput.model_validate(d)
            device.is_current_device = d.get("sessionTokenId") == session_token_id
            results.append(device)

        return Response(
            status_code=200,
            content_type="application/json",
            body=DeviceListAdapter.dump_json(results, by_alias=True).decode(),
        )
