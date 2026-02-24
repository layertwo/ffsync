"""OAuthAuthorization route — POST /v1/oauth/authorization"""

import json

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.fxa_token_manager import FxATokenManager
from src.services.oauth_code_manager import OAuthCodeManager
from src.shared.base_route import BaseRoute


class OAuthAuthorizationRoute(BaseRoute):
    """Issue an OAuth authorization code authenticated with a session token."""

    def __init__(
        self,
        token_manager: FxATokenManager,
        oauth_code_manager: OAuthCodeManager,
    ):
        self._token_manager = token_manager
        self._oauth_code_manager = oauth_code_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/v1/oauth/authorization")
        def handle_oauth_authorization():
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

        client_id = body.get("client_id")
        scope = body.get("scope")
        state = body.get("state")

        if not client_id:
            return self._error(400, 107, "Missing client_id")
        if not scope:
            return self._error(400, 107, "Missing scope")
        if not state:
            return self._error(400, 107, "Missing state")

        code_challenge = body.get("code_challenge", "")
        code_challenge_method = body.get("code_challenge_method", "S256")

        code = self._oauth_code_manager.create_authorization_code(
            uid=uid,
            client_id=client_id,
            scope=scope,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "code": code,
                    "state": state,
                    "redirect": "urn:ietf:wg:oauth:2.0:oob",
                }
            ),
        )

    @staticmethod
    def _error(status: int, errno: int, message: str) -> Response:
        return Response(
            status_code=status,
            content_type="application/json",
            body=json.dumps({"code": status, "errno": errno, "message": message}),
        )
