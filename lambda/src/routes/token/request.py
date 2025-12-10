"""RequestToken route for Firefox Sync Token Server"""

import json
import re
import time

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

# X-Client-State validation pattern: hexadecimal string, max 32 characters
CLIENT_STATE_PATTERN = re.compile(r"^[a-fA-F0-9]{0,32}$")


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

            # Extract request metadata for logging
            request_path = event.get("path", "/1.0/sync/1.5")
            http_method = event.get("httpMethod", "POST")
            source_ip = (event.get("requestContext") or {}).get("identity", {}).get("sourceIp")
            user_agent = (event.get("headers") or {}).get("user-agent") or (
                event.get("headers") or {}
            ).get("User-Agent")

            # Extract and validate Authorization header
            auth_header = self._get_authorization_header(event)
            if not auth_header:
                return self._error_response(
                    status_code=StatusCode.UNAUTHORIZED,
                    error_type="invalid-credentials",
                    location="header",
                    name="Authorization",
                    description="Missing Authorization header",
                    path=request_path,
                    http_method=http_method,
                    source_ip=source_ip,
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
                    path=request_path,
                    http_method=http_method,
                    source_ip=source_ip,
                )

            # Extract and validate X-Client-State header
            client_state = self._get_client_state_header(event)
            if client_state is not None and not self._is_valid_client_state(client_state):
                return self._error_response(
                    status_code=StatusCode.BAD_REQUEST,
                    error_type="invalid-request",
                    location="header",
                    name="X-Client-State",
                    description="Invalid X-Client-State format. Must be hexadecimal, max 32 chars",
                    path=request_path,
                    http_method=http_method,
                    source_ip=source_ip,
                    client_state=client_state,
                )

            # Default to empty string if header is absent
            client_state = client_state or ""

            logger.info(
                "Token request received",
                extra={
                    "path": request_path,
                    "http_method": http_method,
                    "source_ip": source_ip,
                    "user_agent": user_agent,
                    "has_client_state": bool(client_state),
                },
            )

            # Validate OIDC token and extract user identifier
            claims = self.oidc_validator.validate_token(token)
            user_id = claims.sub
            logger.info(
                "OIDC token validated",
                extra={
                    "user_id": user_id,
                    "issuer": claims.iss,
                    "token_expiry": claims.exp,
                },
            )

            # Get or create user record (with client_state for key rotation tracking)
            user_record = self.user_manager.get_or_create_user(user_id, client_state)
            logger.info(
                "User record retrieved",
                extra={
                    "user_id": user_id,
                    "generation": user_record.generation,
                    "client_state_changed": (
                        user_record.client_state != client_state
                        if hasattr(user_record, "client_state")
                        else None
                    ),
                },
            )

            # Generate token response
            token_response = self.token_generator.generate_token(
                user_id=user_id,
                generation=user_record.generation,
            )
            logger.info(
                "Token issued successfully",
                extra={
                    "user_id": user_id,
                    "duration": token_response.duration,
                    "api_endpoint": token_response.api_endpoint,
                    "status_code": 200,
                },
            )

            return Response(
                status_code=StatusCode.OK,
                content_type="application/json",
                body=token_response.to_json(),
                headers={"X-Timestamp": str(int(time.time()))},
            )

        except InvalidCredentialsError as e:
            return self._error_response(
                status_code=StatusCode.UNAUTHORIZED,
                error_type="invalid-credentials",
                location="header",
                name="Authorization",
                description=str(e),
            )

        except InvalidTokenError as e:
            return self._error_response(
                status_code=StatusCode.UNAUTHORIZED,
                error_type="invalid-credentials",
                location="header",
                name="Authorization",
                description=str(e),
            )

        except ValidationException as e:
            return self._error_response(
                status_code=StatusCode.BAD_REQUEST,
                error_type="invalid-request",
                location="body",
                name="request",
                description=str(e),
            )

        except ServiceUnavailableError as e:
            return self._error_response(
                status_code=StatusCode.SERVICE_UNAVAILABLE,
                error_type="service-unavailable",
                location="server",
                name="service",
                description=str(e),
                log_level="error",
            )

        except Exception as e:
            return self._error_response(
                status_code=StatusCode.INTERNAL_SERVER_ERROR,
                error_type="internal-error",
                location="server",
                name="service",
                description="An unexpected error occurred",
                log_level="exception",
                exception_type=type(e).__name__,
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

    def _get_client_state_header(self, event: dict) -> str | None:
        """
        Extract X-Client-State header from event.

        Handles case-insensitive header lookup.

        Args:
            event: API Gateway proxy event

        Returns:
            X-Client-State header value or None if not present
        """
        headers = event.get("headers") or {}
        # API Gateway normalizes headers to lowercase
        return headers.get("x-client-state") or headers.get("X-Client-State")

    def _is_valid_client_state(self, client_state: str) -> bool:
        """
        Validate X-Client-State format.

        Must be a hexadecimal string of up to 32 characters.

        Args:
            client_state: X-Client-State header value

        Returns:
            True if valid, False otherwise
        """
        return bool(CLIENT_STATE_PATTERN.match(client_state))

    def _error_response(
        self,
        status_code: StatusCode,
        error_type: str,
        location: str,
        name: str,
        description: str,
        log_level: str = "warning",
        **extra_log_fields,
    ) -> Response:
        """
        Build error response in Firefox Sync format and log the error.

        Args:
            status_code: HTTP status code
            error_type: Error type identifier
            location: Error location (header, body, query, request, server)
            name: Field name that caused the error
            description: Human-readable error description
            log_level: Log level to use ("warning", "error", or "exception")
            **extra_log_fields: Additional fields to include in log output

        Returns:
            Response with error body and X-Timestamp header
        """
        # Build log context
        log_extra = {
            "status_code": status_code.value,
            "error_type": error_type,
            "location": location,
            "field": name,
            "description": description,
            **extra_log_fields,
        }

        # Log at appropriate level
        log_message = f"Token request failed: {description}"
        if log_level == "error":
            logger.error(log_message, extra=log_extra)
        elif log_level == "exception":
            logger.exception(log_message, extra=log_extra)
        else:
            logger.warning(log_message, extra=log_extra)

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
            headers={"X-Timestamp": str(int(time.time()))},
        )
