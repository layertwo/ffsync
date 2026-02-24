"""ScopedKeyData route — POST /v1/account/scoped-key-data"""

import json

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.auth_account_manager import AuthAccountManager
from src.services.fxa_token_manager import FxATokenManager
from src.shared.base_route import BaseRoute


class ScopedKeyDataRoute(BaseRoute):
    """Return key metadata for sync encryption key derivation."""

    def __init__(
        self,
        account_manager: AuthAccountManager,
        token_manager: FxATokenManager,
    ):
        self._account_manager = account_manager
        self._token_manager = token_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/v1/account/scoped-key-data")
        def handle_scoped_key_data():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        # Authenticate via session token with Hawk HMAC verification
        headers = event.headers or {}
        auth_header = headers.get("authorization", "")
        if not auth_header:
            return self._error(401, 110, "Missing or invalid authorization")

        host = headers.get("host", "localhost")
        port = headers.get("x-forwarded-port", "443")
        method = event.http_method
        path = event.path

        uid = self._token_manager.verify_session_hawk(auth_header, method, path, host, port)
        if uid is None:
            return self._error(401, 110, "Invalid or expired session token")

        # Parse body
        body_str = event.body
        if not body_str:
            return self._error(400, 107, "Missing request body")

        try:
            body = json.loads(body_str)
        except (json.JSONDecodeError, TypeError):
            return self._error(400, 107, "Invalid JSON body")

        scope = body.get("scope")
        if not scope:
            return self._error(400, 107, "Missing scope")

        # Look up account for createdAt and keyRotationSecret
        account = self._account_manager.get_account_by_uid(uid)
        if account is None:
            return self._error(401, 110, "Account not found")

        created_at = account.get("createdAt", 0)
        key_rotation_secret = account.get("keyRotationSecret", "00" * 32)

        # Return key metadata for each scope
        result = {}
        for s in scope.split():
            result[s] = {
                "identifier": s,
                "keyRotationSecret": key_rotation_secret,
                "keyRotationTimestamp": created_at,
            }

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps(result),
        )

    @staticmethod
    def _error(status: int, errno: int, message: str) -> Response:
        return Response(
            status_code=status,
            content_type="application/json",
            body=json.dumps({"code": status, "errno": errno, "message": message}),
        )
