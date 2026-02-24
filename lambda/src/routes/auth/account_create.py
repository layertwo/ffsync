"""AccountCreate route — POST /v1/account/create"""

import json
import re
import uuid

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.auth_account_manager import AuthAccountManager
from src.services.fxa_crypto import derive_verify_hash, generate_random_bytes
from src.services.fxa_token_manager import FxATokenManager
from src.services.oidc_validator import OIDCValidator
from src.shared.base_route import BaseRoute

BEARER_PATTERN = re.compile(r"^Bearer\s+(.+)$", re.IGNORECASE)
AUTH_PW_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AccountCreateRoute(BaseRoute):
    """Create an FxA account linked to an OIDC identity."""

    def __init__(
        self,
        account_manager: AuthAccountManager,
        token_manager: FxATokenManager,
        oidc_validator: OIDCValidator,
    ):
        self._account_manager = account_manager
        self._token_manager = token_manager
        self._oidc_validator = oidc_validator

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/v1/account/create")
        def handle_account_create():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        # Validate OIDC Bearer token
        headers = event.headers or {}
        auth_header = headers.get("authorization")
        if not auth_header:
            return self._error(401, 110, "Missing Authorization header")

        match = BEARER_PATTERN.match(auth_header)
        if not match:
            return self._error(401, 110, "Invalid Authorization header")

        try:
            claims = self._oidc_validator.validate_token(match.group(1))
        except Exception:
            return self._error(401, 110, "Invalid OIDC token")

        # Parse body
        body_str = event.body
        if not body_str:
            return self._error(400, 107, "Missing request body")

        try:
            body = json.loads(body_str)
        except (json.JSONDecodeError, TypeError):
            return self._error(400, 107, "Invalid JSON body")

        email = body.get("email")
        auth_pw_hex = body.get("authPW")
        if not email:
            return self._error(400, 107, "Missing email")
        if not auth_pw_hex:
            return self._error(400, 107, "Missing authPW")

        # Validate input formats
        if "@" not in email:
            return self._error(400, 107, "Invalid email format")
        if not AUTH_PW_PATTERN.match(auth_pw_hex):
            return self._error(400, 107, "Invalid authPW format")

        # Derive verifyHash from authPW
        auth_pw = bytes.fromhex(auth_pw_hex)
        verify_hash = derive_verify_hash(auth_pw).hex()

        # Generate random keys
        k_a = generate_random_bytes(32).hex()
        wrap_kb = generate_random_bytes(32).hex()
        key_rotation_secret = generate_random_bytes(32).hex()

        uid = uuid.uuid4().hex

        # Create account
        try:
            self._account_manager.create_account(
                uid=uid,
                email=email,
                verify_hash=verify_hash,
                k_a=k_a,
                wrap_kb=wrap_kb,
                oidc_sub=claims.sub,
                key_rotation_secret=key_rotation_secret,
            )
        except ValueError:
            return self._error(409, 101, "Account already exists")

        # Create tokens
        session_token = self._token_manager.create_session_token(uid)
        key_fetch_token = self._token_manager.create_key_fetch_token(uid)

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "uid": uid,
                    "sessionToken": session_token.hex(),
                    "keyFetchToken": key_fetch_token.hex(),
                    "verified": True,
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
