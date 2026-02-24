"""OIDCDiscovery route — GET /.well-known/openid-configuration"""

import json

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.jwt_service import JWTService
from src.shared.base_route import BaseRoute


class OIDCDiscoveryRoute(BaseRoute):
    """Return OpenID Connect discovery metadata."""

    def __init__(self, jwt_service: JWTService):
        self._jwt_service = jwt_service

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/.well-known/openid-configuration")
        def handle_oidc_discovery():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        issuer = self._jwt_service.issuer

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "issuer": issuer,
                    "authorization_endpoint": f"{issuer}/v1/oauth/authorization",
                    "token_endpoint": f"{issuer}/v1/oauth/token",
                    "jwks_uri": f"{issuer}/v1/jwks",
                    "response_types_supported": ["code"],
                    "subject_types_supported": ["public"],
                    "id_token_signing_alg_values_supported": ["RS256"],
                }
            ),
        )
