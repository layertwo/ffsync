"""JWKS route — GET /v1/jwks"""

import json
from typing import Any

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.services.jwt_service import JWTService
from src.shared.base_route import BaseRoute


class JWKSRoute(BaseRoute):
    """Return JSON Web Key Set containing the public signing keys."""

    def __init__(self, jwt_service: JWTService):
        self._jwt_service = jwt_service

    def bind(self, app: APIGatewayRestResolver) -> None:
        @app.get("/v1/jwks")
        def handle_jwks() -> Response[Any]:
            return self.handle(app.current_event)

    def handle(self, event: APIGatewayProxyEvent) -> Response:
        jwk = self._jwt_service.get_public_key_jwk()

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps({"keys": [jwk]}),
        )
