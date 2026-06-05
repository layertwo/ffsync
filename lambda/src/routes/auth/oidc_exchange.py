"""OIDC exchange routes — GET /v1/oidc/config and POST /v1/oidc/exchange"""

import json

import requests as http_requests
from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.auth_account_manager import AuthAccountManager
from src.services.oidc_validator import OIDCValidator
from src.shared.base_route import BaseRoute
from src.shared.models import OIDCExchangeOutput

logger = Logger()


class OIDCProviderConfigRoute(BaseRoute):
    """Return the external OIDC provider's authorization endpoint."""

    def __init__(self, oidc_validator: OIDCValidator):
        self._oidc_validator = oidc_validator

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/v1/oidc/config")
        def handle_oidc_provider_config():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        try:
            config = self._oidc_validator.discover_provider_config()
        except Exception:
            logger.exception("Failed to discover OIDC provider config")
            return Response(
                status_code=503,
                content_type="application/json",
                body=json.dumps({"message": "OIDC provider unavailable"}),
            )

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps({"authorization_endpoint": config.authorization_endpoint}),
        )


class OIDCCodeExchangeRoute(BaseRoute):
    """Exchange an OIDC authorization code for tokens server-side."""

    def __init__(
        self,
        oidc_validator: OIDCValidator,
        account_manager: AuthAccountManager,
    ):
        self._oidc_validator = oidc_validator
        self._account_manager = account_manager

    def bind(self, app: APIGatewayRestResolver):
        @app.post("/v1/oidc/exchange")
        def handle_oidc_code_exchange():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        # Parse request body
        try:
            body = json.loads(event.body or "{}")
        except json.JSONDecodeError, TypeError:
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps({"message": "Invalid JSON body"}),
            )

        code = body.get("code")
        code_verifier = body.get("code_verifier")
        redirect_uri = body.get("redirect_uri")

        if not code or not code_verifier or not redirect_uri:
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps(
                    {"message": "Missing required fields: code, code_verifier, redirect_uri"}
                ),
            )

        # 1. Discover provider endpoints
        try:
            provider_config = self._oidc_validator.discover_provider_config()
        except Exception:
            logger.exception("Failed to discover OIDC provider config")
            return Response(
                status_code=503,
                content_type="application/json",
                body=json.dumps({"message": "OIDC provider unavailable"}),
            )

        # 2. Exchange code for tokens at the provider's token endpoint
        try:
            token_response = http_requests.post(
                provider_config.token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self._oidc_validator.client_id,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
        except http_requests.exceptions.RequestException:
            logger.exception("Token exchange request failed")
            return Response(
                status_code=502,
                content_type="application/json",
                body=json.dumps({"message": "Failed to exchange code with OIDC provider"}),
            )

        if not token_response.ok:
            logger.error(
                "Token exchange failed: %s %s",
                token_response.status_code,
                token_response.text,
            )
            return Response(
                status_code=401,
                content_type="application/json",
                body=json.dumps({"message": "Token exchange failed"}),
            )

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return Response(
                status_code=502,
                content_type="application/json",
                body=json.dumps({"message": "No access token in provider response"}),
            )

        # 3. Validate the access token
        try:
            self._oidc_validator.validate_token(access_token)
        except Exception:
            logger.exception("Access token validation failed")
            return Response(
                status_code=401,
                content_type="application/json",
                body=json.dumps({"message": "Access token validation failed"}),
            )

        # 4. Fetch userinfo to get email
        try:
            userinfo_response = http_requests.get(
                provider_config.userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
        except http_requests.exceptions.RequestException:
            logger.exception("Userinfo request failed")
            return Response(
                status_code=502,
                content_type="application/json",
                body=json.dumps({"message": "Failed to fetch user info from OIDC provider"}),
            )

        if not userinfo_response.ok:
            logger.error(
                "Userinfo request failed: %s %s",
                userinfo_response.status_code,
                userinfo_response.text,
            )
            return Response(
                status_code=502,
                content_type="application/json",
                body=json.dumps({"message": "Failed to fetch user info from OIDC provider"}),
            )

        userinfo = userinfo_response.json()
        email = userinfo.get("email")
        if not email:
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps(
                    {
                        "message": "OIDC provider did not return an email. Ensure the email scope is granted."
                    }
                ),
            )

        # 5. Check if account exists
        account = self._account_manager.get_account_by_email(email)

        result = OIDCExchangeOutput(
            email=email,
            access_token=access_token,
            account_exists=account is not None,
        )
        return Response(
            status_code=200,
            content_type="application/json",
            body=result.model_dump_json(),
        )
