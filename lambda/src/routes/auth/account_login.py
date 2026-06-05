"""AccountLogin route — POST /v1/account/login"""

import json
import re

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.auth_account_manager import AuthAccountManager
from src.services.fxa_crypto import constant_time_compare, derive_verify_hash
from src.services.fxa_token_manager import FxATokenManager
from src.shared.base_route import BaseRoute
from src.shared.models import AccountLoginOutput

AUTH_PW_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AccountLoginRoute(BaseRoute):
    """Verify password and issue session/key-fetch tokens."""

    def __init__(
        self,
        account_manager: AuthAccountManager,
        token_manager: FxATokenManager,
    ):
        self._account_manager = account_manager
        self._token_manager = token_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/v1/account/login")
        def handle_account_login():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        # Parse body
        body_str = event.body
        if not body_str:
            return self._error(400, 107, "Missing request body")

        try:
            body = json.loads(body_str)
        except json.JSONDecodeError, TypeError:
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

        # Look up account
        account = self._account_manager.get_account_by_email(email)
        if account is None:
            return self._error(400, 102, "Unknown account")

        # Verify password
        auth_pw = bytes.fromhex(auth_pw_hex)
        computed_verify_hash = derive_verify_hash(auth_pw)
        stored_verify_hash = bytes.fromhex(account["verifyHash"])

        if not constant_time_compare(computed_verify_hash, stored_verify_hash):
            return self._error(400, 103, "Incorrect password")

        uid = account["uid"]

        # Backfill OIDCSUB# lookup record if missing (for accounts created before this index)
        self._account_manager.ensure_oidcsub_record(uid, account.get("oidcSub", ""))

        # Create session token (always)
        session_token = self._token_manager.create_session_token(uid)

        result = AccountLoginOutput(
            uid=uid,
            session_token=session_token.hex(),
            verified=True,
        )

        # Create key-fetch token if keys=true
        params = event.query_string_parameters or {}
        if params.get("keys") == "true":
            key_fetch_token = self._token_manager.create_key_fetch_token(uid)
            result.key_fetch_token = key_fetch_token.hex()

        return Response(
            status_code=200,
            content_type="application/json",
            body=result.model_dump_json(by_alias=True, exclude_none=True),
        )

    @staticmethod
    def _error(status: int, errno: int, message: str) -> Response:
        return Response(
            status_code=status,
            content_type="application/json",
            body=json.dumps({"code": status, "errno": errno, "message": message}),
        )
