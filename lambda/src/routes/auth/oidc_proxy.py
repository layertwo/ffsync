"""OIDC Proxy routes — proxy OIDC provider calls through the auth server.

Eliminates CORS issues by making browser-to-OIDC-provider calls server-side.
The authorization endpoint is NOT proxied since it uses a full-page redirect.
"""

import json

import requests as http_requests
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.oidc_validator import OIDCValidator
from src.shared.base_route import BaseRoute


class OIDCProxyConfigRoute(BaseRoute):
    """GET /v1/oidc/config — return OIDC provider discovery with proxied endpoints."""

    def __init__(self, oidc_validator: OIDCValidator, auth_server_base_url: str):
        self._oidc_validator = oidc_validator
        self._auth_server_base_url = auth_server_base_url

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/v1/oidc/config")
        def handle_oidc_proxy_config():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        try:
            config = self._oidc_validator.discover_provider_config()
            return Response(
                status_code=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "issuer": config.issuer,
                        "authorization_endpoint": config.authorization_endpoint,
                        "token_endpoint": f"{self._auth_server_base_url}/v1/oidc/token",
                        "userinfo_endpoint": f"{self._auth_server_base_url}/v1/oidc/userinfo",
                    }
                ),
            )
        except Exception:
            return Response(
                status_code=502,
                content_type="application/json",
                body=json.dumps({"error": "Failed to fetch OIDC provider configuration"}),
            )


class OIDCProxyTokenRoute(BaseRoute):
    """POST /v1/oidc/token — proxy token exchange to the OIDC provider."""

    def __init__(self, oidc_validator: OIDCValidator):
        self._oidc_validator = oidc_validator

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/v1/oidc/token")
        def handle_oidc_proxy_token():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        try:
            config = self._oidc_validator.discover_provider_config()

            body = event.get("body", "")
            resp = http_requests.post(
                config.token_endpoint,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )

            return Response(
                status_code=resp.status_code,
                content_type="application/json",
                body=resp.text,
            )
        except Exception:
            return Response(
                status_code=502,
                content_type="application/json",
                body=json.dumps({"error": "Failed to exchange token with OIDC provider"}),
            )


class OIDCProxyUserinfoRoute(BaseRoute):
    """GET /v1/oidc/userinfo — proxy userinfo request to the OIDC provider."""

    def __init__(self, oidc_validator: OIDCValidator):
        self._oidc_validator = oidc_validator

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/v1/oidc/userinfo")
        def handle_oidc_proxy_userinfo():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        try:
            config = self._oidc_validator.discover_provider_config()

            headers = {}
            auth_header = event.get("headers", {}).get("Authorization", "")
            if auth_header:
                headers["Authorization"] = auth_header

            resp = http_requests.get(
                config.userinfo_endpoint,
                headers=headers,
                timeout=10,
            )

            return Response(
                status_code=resp.status_code,
                content_type="application/json",
                body=resp.text,
            )
        except Exception:
            return Response(
                status_code=502,
                content_type="application/json",
                body=json.dumps({"error": "Failed to fetch user info from OIDC provider"}),
            )
