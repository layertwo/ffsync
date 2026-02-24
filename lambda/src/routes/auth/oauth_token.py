"""OAuthToken route — POST /v1/oauth/token"""

import hashlib
import json
import time

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.auth_account_manager import AuthAccountManager
from src.services.jwt_service import JWTService
from src.services.oauth_code_manager import OAuthCodeManager
from src.shared.base_route import BaseRoute

DEFAULT_TTL = 900  # 15 minutes
MAX_TTL = 3600  # 1 hour maximum


class OAuthTokenRoute(BaseRoute):
    """Exchange authorization code or refresh token for JWT access token."""

    def __init__(
        self,
        oauth_code_manager: OAuthCodeManager,
        jwt_service: JWTService,
        account_manager: AuthAccountManager,
    ):
        self._oauth_code_manager = oauth_code_manager
        self._jwt_service = jwt_service
        self._account_manager = account_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/v1/oauth/token")
        def handle_oauth_token():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        body_str = event.body
        if not body_str:
            return self._error(400, 107, "Missing request body")

        try:
            body = json.loads(body_str)
        except (json.JSONDecodeError, TypeError):
            return self._error(400, 107, "Invalid JSON body")

        grant_type = body.get("grant_type")
        if not grant_type:
            return self._error(400, 107, "Missing grant_type")

        if grant_type == "authorization_code":
            return self._handle_authorization_code(body)
        elif grant_type == "refresh_token":
            return self._handle_refresh_token(body)
        else:
            return self._error(400, 107, f"Unsupported grant_type: {grant_type}")

    def _handle_authorization_code(self, body: dict) -> Response:
        code = body.get("code")
        if not code:
            return self._error(400, 107, "Missing code")

        code_verifier = body.get("code_verifier")

        # Consume authorization code (single-use)
        code_data = self._oauth_code_manager.consume_authorization_code(code)
        if code_data is None:
            return self._error(400, 110, "Invalid or expired authorization code")

        # Verify PKCE if code_challenge was provided
        if code_data["codeChallenge"]:
            if not code_verifier:
                return self._error(400, 107, "Missing code_verifier")
            if not OAuthCodeManager.verify_code_challenge(
                code_verifier,
                code_data["codeChallenge"],
                code_data["codeChallengeMethod"],
            ):
                return self._error(400, 110, "Invalid code_verifier")

        uid = code_data["uid"]
        scope = code_data["scope"]
        client_id = code_data["clientId"]

        # Look up account to get oidcSub for the JWT sub claim
        account = self._account_manager.get_account_by_uid(uid)
        if account is None:
            return self._error(400, 110, "Account not found")

        sub = account["oidcSub"]
        ttl = min(int(body.get("ttl", DEFAULT_TTL)), MAX_TTL)

        # Sign JWT
        access_token = self._jwt_service.sign_jwt(
            sub=sub,
            scope=scope,
            ttl=ttl,
            client_id=client_id,
        )

        # Create refresh token
        refresh_token = self._oauth_code_manager.create_refresh_token(
            uid=uid,
            client_id=client_id,
            scope=scope,
        )

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "expires_in": ttl,
                    "scope": scope,
                    "refresh_token": refresh_token,
                    "auth_at": int(time.time()),
                }
            ),
        )

    def _handle_refresh_token(self, body: dict) -> Response:
        refresh_token = body.get("refresh_token")
        if not refresh_token:
            return self._error(400, 107, "Missing refresh_token")

        token_hash = hashlib.sha256(refresh_token.encode("ascii")).hexdigest()
        token_data = self._oauth_code_manager.consume_refresh_token(token_hash)
        if token_data is None:
            return self._error(400, 110, "Invalid or expired refresh token")

        uid = token_data["uid"]
        scope = body.get("scope", token_data["scope"])
        client_id = token_data["clientId"]

        # Validate requested scope is a subset of the original grant
        requested_scopes = set(scope.split())
        allowed_scopes = set(token_data["scope"].split())
        if not requested_scopes.issubset(allowed_scopes):
            return self._error(400, 165, "Requested scope exceeds granted scope")

        # Look up account to get oidcSub
        account = self._account_manager.get_account_by_uid(uid)
        if account is None:
            return self._error(400, 110, "Account not found")

        sub = account["oidcSub"]
        ttl = min(int(body.get("ttl", DEFAULT_TTL)), MAX_TTL)

        access_token = self._jwt_service.sign_jwt(
            sub=sub,
            scope=scope,
            ttl=ttl,
            client_id=client_id,
        )

        # Create new refresh token
        new_refresh_token = self._oauth_code_manager.create_refresh_token(
            uid=uid,
            client_id=client_id,
            scope=scope,
        )

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "access_token": access_token,
                    "token_type": "bearer",
                    "expires_in": ttl,
                    "scope": scope,
                    "refresh_token": new_refresh_token,
                    "auth_at": int(time.time()),
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
