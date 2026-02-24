"""AccountStatus route — GET /v1/account/status"""

import json

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.auth_account_manager import AuthAccountManager
from src.shared.base_route import BaseRoute


class AccountStatusRoute(BaseRoute):
    """Check whether an account exists for a given email."""

    def __init__(self, account_manager: AuthAccountManager):
        self._account_manager = account_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/v1/account/status")
        def handle_account_status():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        params = event.query_string_parameters or {}
        email = params.get("email")
        if not email:
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps({"code": 400, "errno": 107, "message": "Missing email parameter"}),
            )

        account = self._account_manager.get_account_by_email(email)
        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps({"exists": account is not None}),
        )
