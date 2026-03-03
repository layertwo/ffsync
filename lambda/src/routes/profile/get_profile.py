"""GetProfile route — GET /v1/profile (OAuth Bearer auth)"""

import json

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.auth_account_manager import AuthAccountManager
from src.services.jwt_verifier import JWTVerifier
from src.shared.base_route import BaseRoute
from src.shared.exceptions import InvalidTokenError


class GetProfileRoute(BaseRoute):
    """Return basic profile info for the authenticated user via OAuth Bearer token."""

    def __init__(
        self,
        jwt_verifier: JWTVerifier,
        auth_account_manager: AuthAccountManager,
    ):
        self._jwt_verifier = jwt_verifier
        self._auth_account_manager = auth_account_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/v1/profile")
        def handle_get_profile():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        headers = event.headers or {}
        auth_header = headers.get("authorization", "")

        if not auth_header:
            return self._error(401, 110, "Missing or invalid authorization")

        if not auth_header.startswith("Bearer "):
            return self._error(401, 110, "Missing or invalid authorization")

        token = auth_header[len("Bearer ") :]

        try:
            claims = self._jwt_verifier.validate_token(token)
        except InvalidTokenError:
            return self._error(401, 110, "Invalid or expired token")

        # Look up account by fxa_uid (from JWT) or fall back to oidcSub lookup
        account = None
        if claims.fxa_uid:
            account = self._auth_account_manager.get_account_by_uid(claims.fxa_uid)
        if account is None:
            account = self._auth_account_manager.get_account_by_oidc_sub(claims.sub)
        if account is None:
            return self._error(401, 110, "Account not found")

        uid = account["uid"]
        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "uid": uid,
                    "email": account["email"],
                    "locale": "en-US",
                    "avatar": "",
                    "avatarDefault": True,
                    "sub": uid,
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
