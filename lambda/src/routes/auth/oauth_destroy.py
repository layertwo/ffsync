"""OAuthDestroy route — POST /v1/oauth/destroy"""

import hashlib
import json

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.oauth_code_manager import OAuthCodeManager
from src.shared.base_route import BaseRoute


class OAuthDestroyRoute(BaseRoute):
    """Revoke an OAuth token (per RFC 7009)."""

    def __init__(self, oauth_code_manager: OAuthCodeManager):
        self._oauth_code_manager = oauth_code_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/v1/oauth/destroy")
        def handle_oauth_destroy():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        body_str = event.body
        if not body_str:
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps({"code": 400, "errno": 107, "message": "Missing request body"}),
            )

        try:
            body = json.loads(body_str)
        except json.JSONDecodeError, TypeError:
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps({"code": 400, "errno": 107, "message": "Invalid JSON body"}),
            )

        token = body.get("token")
        if not token:
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps({"code": 400, "errno": 107, "message": "Missing token"}),
            )

        # Hash the token and delete from DynamoDB (if it exists)
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        self._oauth_code_manager.delete_refresh_token(token_hash)

        # Per RFC 7009, always return 200 regardless of whether the token existed
        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps({}),
        )
