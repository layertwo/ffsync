"""AccountKeys route — GET /v1/account/keys"""

import json

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.auth_account_manager import AuthAccountManager
from src.services.fxa_crypto import derive_key_request_key, encrypt_key_bundle
from src.services.fxa_token_manager import KEY_FETCH_TOKEN_INFO, FxATokenManager
from src.shared.base_route import BaseRoute


class AccountKeysRoute(BaseRoute):
    """Return encrypted kA + wrapKB bundle using key-fetch token."""

    def __init__(
        self,
        account_manager: AuthAccountManager,
        token_manager: FxATokenManager,
    ):
        self._account_manager = account_manager
        self._token_manager = token_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/v1/account/keys")
        def handle_account_keys():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        # Authenticate via key-fetch token with Hawk HMAC verification
        headers = event.headers or {}
        auth_header = headers.get("authorization", "")
        if not auth_header:
            return self._error(401, 110, "Missing or invalid authorization")

        host = headers.get("host", "localhost")
        port = headers.get("x-forwarded-port", "443")
        method = event.http_method
        path = event.path

        # Consume the key-fetch token with Hawk HMAC verification (single-use)
        token_data = self._token_manager.verify_keyfetch_hawk(auth_header, method, path, host, port)
        if token_data is None:
            return self._error(401, 110, "Invalid or expired keyFetchToken")

        uid = token_data["uid"]
        raw_token = bytes.fromhex(token_data["keyFetchToken"])

        # Look up account
        account = self._account_manager.get_account_by_uid(uid)
        if account is None:
            return self._error(401, 110, "Account not found")

        k_a = bytes.fromhex(account["kA"])
        wrap_kb = bytes.fromhex(account["wrapKB"])

        # Derive keyRequestKey from the raw key-fetch token
        key_request_key = derive_key_request_key(raw_token, KEY_FETCH_TOKEN_INFO)

        # Encrypt key bundle
        bundle = encrypt_key_bundle(key_request_key, k_a, wrap_kb)

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps({"bundle": bundle.hex()}),
        )

    @staticmethod
    def _error(status: int, errno: int, message: str) -> Response:
        return Response(
            status_code=status,
            content_type="application/json",
            body=json.dumps({"code": status, "errno": errno, "message": message}),
        )
