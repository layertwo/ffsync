"""AccountProfile route — GET /v1/account/profile"""

import json

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.auth_account_manager import AuthAccountManager
from src.services.fxa_token_manager import FxATokenManager
from src.shared.base_route import BaseRoute
from src.shared.utils import extract_hawk_request_params


class AccountProfileRoute(BaseRoute):
    """Return basic profile info for the authenticated user."""

    def __init__(
        self,
        account_manager: AuthAccountManager,
        token_manager: FxATokenManager,
    ):
        self._account_manager = account_manager
        self._token_manager = token_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/v1/account/profile")
        def handle_account_profile():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        # Authenticate via session token with Hawk HMAC verification
        headers = event.headers or {}
        auth_header = headers.get("authorization", "")
        if not auth_header:
            return self._error(401, 110, "Missing or invalid authorization")

        method, path, host, port = extract_hawk_request_params(event)

        uid = self._token_manager.verify_session_hawk(auth_header, method, path, host, port)
        if uid is None:
            return self._error(401, 110, "Invalid or expired session token")

        account = self._account_manager.get_account_by_uid(uid)
        if account is None:
            return self._error(401, 110, "Account not found")

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "email": account["email"],
                    "uid": account["uid"],
                    "locale": "en-US",
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
