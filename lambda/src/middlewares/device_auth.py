"""Device route authentication middleware.

Accepts an OAuth refresh token (``Authorization: Bearer <refresh_token>``) in addition
to session Hawk, matching FxA's contract for device registration. Any non-Bearer header
delegates to the session Hawk middleware.
"""

import hashlib

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler, NextMiddleware
from aws_lambda_powertools.metrics import Metrics, MetricUnit

from src.middlewares.hawk_auth import HawkAuthenticationError, HawkAuthMiddleware
from src.services.oauth_code_manager import OAuthCodeManager


class DeviceAuthMiddleware(BaseMiddlewareHandler):

    def __init__(
        self,
        *,
        metrics: Metrics,
        oauth_code_manager: OAuthCodeManager,
        session_hawk: HawkAuthMiddleware,
    ):
        super().__init__()
        self._metrics = metrics
        self._oauth_code_manager = oauth_code_manager
        self._session_hawk = session_hawk

    def handler(self, app: APIGatewayRestResolver, next_middleware: NextMiddleware) -> Response:
        event = app.current_event
        headers = event.headers or {}
        auth_header = headers.get("Authorization") or headers.get("authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            return self._session_hawk.handler(app, next_middleware)

        token = auth_header[len("Bearer ") :]
        try:
            token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        except UnicodeEncodeError:
            # A malformed bearer is a client error, not an internal one.
            self._metrics.add_metric("HawkAuthFailure", MetricUnit.Count, 1)
            raise HawkAuthenticationError("Invalid or expired session token") from None
        record = self._oauth_code_manager.get_refresh_token(token_hash)
        if record is None:
            self._metrics.add_metric("HawkAuthFailure", MetricUnit.Count, 1)
            raise HawkAuthenticationError("Invalid or expired session token")

        event["requestContext"]["hawk_uid"] = record["uid"]
        self._metrics.add_metric("RefreshTokenAuthSuccess", MetricUnit.Count, 1)
        return next_middleware(app)
