"""RequestToken route for Firefox Sync Token Server"""

import json
import re

from aws_lambda_powertools import Logger
from aws_lambda_proxy import API, Response, StatusCode

from src.services.oidc_validator import OIDCValidator
from src.services.token_generator import TokenGenerator
from src.services.user_manager import UserManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    ServiceUnavailableError,
    ValidationException,
)

logger = Logger()

# Bearer token regex pattern
BEARER_TOKEN_PATTERN = re.compile(r"^Bearer\s+(.+)$", re.IGNORECASE)


class RequestTokenRoute(BaseRoute):
    """
    Route handler for RequestToken operation.

    Handles POST /1.0/sync/1.5 requests to exchange OIDC tokens
    for Firefox Sync HAWK credentials.
    """

    def __init__(
        self,
        oidc_validator: OIDCValidator,
        user_manager: UserManager,
        token_generator: TokenGenerator,
    ):
        """
        Initialize CreateTokenRoute with dependencies.

        Args:
            oidc_validator: OIDC token validator
            user_manager: User record manager
            token_generator: HAWK credential generator
        """
        self.oidc_validator = oidc_validator
        self.user_manager = user_manager
        self.token_generator = token_generator

    def bind(self, api: API):
        """Bind this route to the API with POST decorator"""

        @api.post("/1.0/sync/1.5")
        @api.pass_event
        def handle_with_event(event: dict, **kwargs) -> Response:
            # kwargs may contain parsed body from the API framework, which we ignore
            # since we handle body parsing ourselves via the event
            return self.handle(event)

    def handle(self, event: dict) -> Response:
        """
        Handle token creation request.

        Orchestrates the token issuance flow:
        1. Validate request (Content-Type if body present)
        2. Extract and validate Authorization header
        3. Validate OIDC token with provider
        4. Get or create user record
        5. Generate HAWK credentials
        6. Return token response

        Args:
            event: API Gateway proxy event

        Returns:
            Response with token or error
        """
        try:
            # Validate Content-Type if body is present
            validation_error = self._validate_content_type(event)
            if validation_error:
                return validation_error

            # Extract and validate Authorization header
            auth_header = self._get_authorization_header(event)
            if not auth_header:
                return self._error_response(
                    status_code=StatusCode.UNAUTHORIZED,
                    error_type="invalid-credentials",
                    location="header",
                    name="Authorization",
                    description="Missing Authorization header",
                )

            # Extract Bearer token
            token = self._extract_bearer_token(auth_header)
            if token is None:
                return self._error_response(
                    status_code=StatusCode.BAD_REQUEST,
                    error_type="invalid-request",
                    location="header",
                    name="Authorization",
                    description="Malformed Authorization header. Expected: Bearer <token>",
                )

            # Validate OIDC token and extract user identifier
            claims = self.oidc_validator.validate_token(token)
            user_id = claims.sub

            # Get or create user record
            user_record = self.user_manager.get_or_create_user(user_id)

            # Generate token response
            token_response = self.token_generator.generate_token(
                user_id=user_id,
                generation=user_record.generation,
            )

            # Log successful authentication
            logger.info("Token issued successfully", extra={"user_id": user_id})

            return Response(
                status_code=StatusCode.OK,
                content_type="application/json",
                body=token_response.to_json(),
            )

        except InvalidCredentialsError as e:
            logger.warning("Authentication failed", extra={"reason": str(e)})
            return self._error_response(
                status_code=StatusCode.UNAUTHORIZED,
                error_type="invalid-credentials",
                location="header",
                name="Authorization",
                description=str(e),
            )

        except InvalidTokenError as e:
            logger.warning("Invalid token", extra={"reason": str(e)})
            return self._error_response(
                status_code=StatusCode.UNAUTHORIZED,
                error_type="invalid-credentials",
                location="header",
                name="Authorization",
                description=str(e),
            )

        except ValidationException as e:
            logger.warning("Validation error", extra={"reason": str(e)})
            return self._error_response(
                status_code=StatusCode.BAD_REQUEST,
                error_type="invalid-request",
                location="body",
                name="request",
                description=str(e),
            )

        except ServiceUnavailableError as e:
            logger.error("Service unavailable", extra={"reason": str(e)})
            return self._error_response(
                status_code=StatusCode.SERVICE_UNAVAILABLE,
                error_type="service-unavailable",
                location="server",
                name="service",
                description=str(e),
            )

        except Exception as e:
            logger.exception("Unexpected error during token issuance")
            return self._error_response(
                status_code=StatusCode.INTERNAL_SERVER_ERROR,
                error_type="internal-error",
                location="server",
                name="service",
                description="An unexpected error occurred",
            )

    def _validate_content_type(self, event: dict) -> Response | None:
        """
        Validate Content-Type header if body is present.

        Args:
            event: API Gateway proxy event

        Returns:
            Error Response if Content-Type is invalid, None if valid
        """
        body = event.get("body")
        if not body:
            return None

        content_type = self._get_content_type(event)
        if content_type and not self._is_valid_content_type(content_type):
            logger.warning("Invalid Content-Type", extra={"content_type": content_type})
            return self._error_response(
                status_code=StatusCode.UNSUPPORTED_MEDIA_TYPE,
                error_type="unsupported-media-type",
                location="header",
                name="Content-Type",
                description=f"Unsupported Content-Type: {content_type}",
            )
        return None

    def _get_content_type(self, event: dict) -> str | None:
        """
        Extract Content-Type header from event.

        Args:
            event: API Gateway proxy event

        Returns:
            Content-Type header value or None
        """
        headers = event.get("headers") or {}
        return headers.get("content-type") or headers.get("Content-Type")

    def _is_valid_content_type(self, content_type: str) -> bool:
        """
        Check if Content-Type is valid for token requests.

        Args:
            content_type: Content-Type header value

        Returns:
            True if valid, False otherwise
        """
        valid_types = ["application/json", "application/x-www-form-urlencoded", "text/plain"]
        content_type_lower = content_type.lower().split(";")[0].strip()
        return content_type_lower in valid_types

    def _get_authorization_header(self, event: dict) -> str | None:
        """
        Extract Authorization header from event.

        Handles case-insensitive header lookup.

        Args:
            event: API Gateway proxy event

        Returns:
            Authorization header value or None
        """
        headers = event.get("headers") or {}
        # API Gateway normalizes headers to lowercase
        return headers.get("authorization") or headers.get("Authorization")

    def _extract_bearer_token(self, auth_header: str) -> str | None:
        """
        Extract Bearer token from Authorization header.

        Args:
            auth_header: Authorization header value

        Returns:
            Bearer token string or None if format is invalid
        """
        match = BEARER_TOKEN_PATTERN.match(auth_header)
        if not match:
            return None
        return match.group(1)

    def _error_response(
        self,
        status_code: StatusCode,
        error_type: str,
        location: str,
        name: str,
        description: str,
    ) -> Response:
        """
        Build error response in Firefox Sync format.

        Args:
            status_code: HTTP status code
            error_type: Error type identifier
            location: Error location (header, body, query, request, server)
            name: Field name that caused the error
            description: Human-readable error description

        Returns:
            Response with error body
        """
        body = {
            "status": error_type,
            "errors": [
                {
                    "location": location,
                    "name": name,
                    "description": description,
                }
            ],
        }
        return Response(
            status_code=status_code,
            content_type="application/json",
            body=json.dumps(body),
        )
