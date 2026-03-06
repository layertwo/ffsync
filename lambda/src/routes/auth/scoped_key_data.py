"""ScopedKeyData route — POST /v1/account/scoped-key-data"""

import json
from typing import Sequence

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler
from pydantic import ValidationError as PydanticValidationError

from src.services.auth_account_manager import AuthAccountManager
from src.shared.base_route import BaseRoute
from src.shared.models import ScopedKeyDataEntry, ScopedKeyDataInput


class ScopedKeyDataRoute(BaseRoute):
    """Return key metadata for sync encryption key derivation."""

    def __init__(
        self,
        account_manager: AuthAccountManager,
        middlewares: Sequence[BaseMiddlewareHandler] = (),
    ):
        self._account_manager = account_manager
        self.middlewares = middlewares

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/v1/account/scoped-key-data", middlewares=list(self.middlewares))
        def handle_scoped_key_data():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        uid = event["requestContext"]["hawk_uid"]

        # Parse and validate body
        body_str = event.body
        if not body_str:
            return self._error(400, 107, "Missing request body")

        try:
            body_input = ScopedKeyDataInput.model_validate_json(body_str)
        except PydanticValidationError:
            return self._error(400, 107, "Missing or invalid scope")

        scope = body_input.scope

        # Look up account for createdAt and keyRotationSecret
        account = self._account_manager.get_account_by_uid(uid)
        if account is None:
            return self._error(401, 110, "Account not found")

        created_at = int(account.get("createdAt", 0))
        key_rotation_secret = account.get("keyRotationSecret", "00" * 32)

        # Return key metadata for each scope
        result = {}
        for s in scope.split():
            entry = ScopedKeyDataEntry(
                identifier=s,
                key_rotation_secret=key_rotation_secret,
                key_rotation_timestamp=created_at,
            )
            result[s] = entry.model_dump(by_alias=True)

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
