"""Unified Hawk authentication middleware.

Handles both storage Hawk (hawk_service) and session Hawk (token_manager)
authentication. Pass hawk_service for storage API, token_manager for auth API
session-authenticated routes.

On success, injects ``hawk_uid`` and ``hawk_token_id`` into event["requestContext"].
On failure, raises HawkAuthenticationError (handle with router exception handler).
"""

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler, NextMiddleware
from aws_lambda_powertools.metrics import Metrics, MetricUnit

from src.services.fxa_token_manager import FxATokenManager
from src.services.hawk_service import HawkService
from src.services.token_generator import TokenGenerator
from src.shared.utils import extract_hawk_request_params


class HawkAuthenticationError(Exception):
    """Raised when Hawk authentication fails (missing header, invalid MAC, expired token)."""


class UidMismatchError(Exception):
    """Raised when the URL uid does not match the authenticated user."""


class HawkAuthMiddleware(BaseMiddlewareHandler):

    def __init__(
        self,
        *,
        metrics: Metrics,
        hawk_service: HawkService | None = None,
        token_manager: FxATokenManager | None = None,
    ):
        super().__init__()
        if not hawk_service and not token_manager:
            raise ValueError("Either hawk_service or token_manager is required")
        self._hawk_service = hawk_service
        self._token_manager = token_manager
        self._metrics = metrics

    def handler(self, app: APIGatewayRestResolver, next_middleware: NextMiddleware) -> Response:
        event = app.current_event

        headers = event.headers or {}
        auth_header = headers.get("Authorization") or headers.get("authorization")
        if not auth_header:
            self._metrics.add_metric("HawkAuthFailure", MetricUnit.Count, 1)
            raise HawkAuthenticationError("Missing or invalid authorization")

        method, path, host, port = extract_hawk_request_params(event)

        try:
            if self._hawk_service:
                self._validate_storage_hawk(event, auth_header, method, path, host, port)
            else:
                self._validate_session_hawk(event, auth_header, method, path, host, port)
        except HawkAuthenticationError, UidMismatchError:
            self._metrics.add_metric("HawkAuthFailure", MetricUnit.Count, 1)
            raise

        self._metrics.add_metric("HawkAuthSuccess", MetricUnit.Count, 1)
        return next_middleware(app)

    def _validate_storage_hawk(self, event, auth_header, method, path, host, port):
        """Validate storage Hawk token and check URL uid matches authenticated user."""
        assert self._hawk_service is not None
        try:
            query_params = event.query_string_parameters
            creds = self._hawk_service.validate(
                auth_header, method, path, host, port, query_params=query_params
            )
        except Exception as e:
            raise HawkAuthenticationError(str(e)) from e

        # Validate URL uid matches authenticated user
        path_params = event.get("pathParameters") or {}
        path_uid = path_params.get("uid")
        if path_uid:
            expected = str(TokenGenerator.generate_uid(creds.user_id, creds.generation))
            if path_uid != expected:
                raise UidMismatchError("uid mismatch")

        event["requestContext"]["hawk_uid"] = creds.user_id

    def _validate_session_hawk(self, event, auth_header, method, path, host, port):
        """Validate FxA session Hawk token."""
        assert self._token_manager is not None
        uid = self._token_manager.verify_session_hawk(auth_header, method, path, host, port)
        if uid is None:
            raise HawkAuthenticationError("Invalid or expired session token")

        event["requestContext"]["hawk_uid"] = uid
        # Inject the Hawk id (session token ID) for device correlation
        event["requestContext"]["hawk_token_id"] = (
            FxATokenManager.extract_token_id_from_hawk_header(auth_header) or ""
        )
