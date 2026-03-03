"""AccountDevicesNotify route — POST /v1/account/devices/notify (no-op)"""

import json
from typing import Sequence

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler

from src.shared.base_route import BaseRoute


class AccountDevicesNotifyRoute(BaseRoute):
    """No-op push notification endpoint for device-to-device messaging."""

    def __init__(self, middlewares: Sequence[BaseMiddlewareHandler] = ()):
        self.middlewares = middlewares

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/v1/account/devices/notify", middlewares=list(self.middlewares))
        def handle_account_devices_notify():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps({}),
        )
