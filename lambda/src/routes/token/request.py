"""RequestToken route for Firefox Sync Token Server"""

import re
import time
from dataclasses import asdict

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response

from src.services.oidc_validator import OIDCValidator
from src.services.token_generator import TokenGenerator
from src.services.user_manager import UserManager
from src.shared.base_route import BaseRoute
from src.shared.exceptions import (
    InvalidClientStateError,
    InvalidCredentialsError,
    InvalidGenerationError,
    InvalidTimestampError,
    InvalidTokenError,
    NewUsersDisabledError,
    ServiceUnavailableError,
    ValidationException,
)
from src.shared.utils import json_dumps

logger = Logger()

BEARER_TOKEN_PATTERN = re.compile(r"^Bearer\s+(.+)$", re.IGNORECASE)
CLIENT_STATE_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{0,32}$")


class RequestTokenRoute(BaseRoute):
    """Route handler for RequestToken operation."""

    def __init__(
        self,
        oidc_validator: OIDCValidator,
        user_manager: UserManager,
        token_generator: TokenGenerator,
    ):
        self.oidc_validator = oidc_validator
        self.user_manager = user_manager
        self.token_generator = token_generator

    def bind(self, app: APIGatewayRestResolver):
        @app.get("/1.0/sync/1.5")
        def handle_request():
            return self.handle(app.current_event)

    def handle(self, event) -> Response:
        """Handle token creation request."""
        try:
            body = event.body
            request_path = event.path or "/1.0/sync/1.5"
            http_method = event.http_method or "GET"

            validation_error = self._validate_content_type(body, event)
            if validation_error:
                return validation_error

            try:
                request_context = event.request_context
                identity = request_context.identity if request_context else None
                source_ip = identity.source_ip if identity else None
            except (KeyError, AttributeError):
                source_ip = None
            headers = event.headers or {}
            user_agent = headers.get("user-agent")

            auth_header = headers.get("authorization")
            if not auth_header:
                return self._error_response(
                    status_code=401,
                    error_type="invalid-credentials",
                    location="header",
                    name="Authorization",
                    description="Missing Authorization header",
                    path=request_path,
                    http_method=http_method,
                    source_ip=source_ip,
                )

            token = self._extract_bearer_token(auth_header)
            if token is None:
                return self._error_response(
                    status_code=400,
                    error_type="invalid-request",
                    location="header",
                    name="Authorization",
                    description="Malformed Authorization header. Expected: Bearer <token>",
                    path=request_path,
                    http_method=http_method,
                    source_ip=source_ip,
                )

            client_state = headers.get("x-client-state")
            if client_state is not None and not self._is_valid_client_state(client_state):
                return self._error_response(
                    status_code=400,
                    error_type="invalid-request",
                    location="header",
                    name="X-Client-State",
                    description="Invalid X-Client-State format. Must be urlsafe-base64 characters (alphanumeric, underscore, hyphen, period), max 32 chars",
                    path=request_path,
                    http_method=http_method,
                    source_ip=source_ip,
                    client_state=client_state,
                )

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

            # Get or create user record FIRST (to get generation)
            user_record = self.user_manager.get_or_create_user(user_id, client_state)

            # Then derive uid from user_id + generation (changes on node reset)
            uid = self.token_generator.generate_uid(user_id, user_record.generation)

            logger.info(
                "User record retrieved",
                extra={
                    "user_id": user_id,
                    "uid": uid,
                    "generation": user_record.generation,
                    "client_state_changed": (
                        user_record.client_state != client_state
                        if hasattr(user_record, "client_state")
                        else None
                    ),
                },
            )

            token_response = self.token_generator.generate_token(
                user_id=user_id,
                uid=uid,
                generation=user_record.generation,
            )
            logger.info(
                "Token issued successfully",
                extra={
                    "uid": uid,
                    "duration": token_response.duration,
                    "api_endpoint": token_response.api_endpoint,
                    "status_code": 200,
                },
            )

            return Response(
                status_code=200,
                content_type="application/json",
                body=json_dumps(asdict(token_response)),
                headers={"X-Timestamp": str(int(time.time()))},
            )

        except InvalidTimestampError as e:
            return self._error_response(
                status_code=401,
                error_type="invalid-timestamp",
                location="header",
                name="Authorization",
                description=str(e),
            )

        except InvalidGenerationError as e:
            return self._error_response(
                status_code=401,
                error_type="invalid-generation",
                location="header",
                name="Authorization",
                description=str(e),
            )

        except InvalidClientStateError as e:
            return self._error_response(
                status_code=401,
                error_type="invalid-client-state",
                location="header",
                name="X-Client-State",
                description=str(e),
            )

        except NewUsersDisabledError as e:
            return self._error_response(
                status_code=401,
                error_type="new-users-disabled",
                location="server",
                name="registration",
                description=str(e),
            )

        except InvalidCredentialsError as e:
            return self._error_response(
                status_code=401,
                error_type="invalid-credentials",
                location="header",
                name="Authorization",
                description=str(e),
            )

        except InvalidTokenError as e:
            return self._error_response(
                status_code=401,
                error_type="invalid-credentials",
                location="header",
                name="Authorization",
                description=str(e),
            )

        except ValidationException as e:
            return self._error_response(
                status_code=400,
                error_type="invalid-request",
                location="body",
                name="request",
                description=str(e),
            )

        except ServiceUnavailableError as e:
            return self._error_response(
                status_code=503,
                error_type="service-unavailable",
                location="server",
                name="service",
                description=str(e),
                log_level="error",
            )

        except Exception as e:
            return self._error_response(
                status_code=500,
                error_type="internal-error",
                location="server",
                name="service",
                description="An unexpected error occurred",
                log_level="exception",
                exception_type=type(e).__name__,
            )

    def _validate_content_type(self, body, event) -> Response | None:
        if not body:
            return None
        headers = event.headers or {}
        content_type = headers.get("content-type")
        if content_type and not self._is_valid_content_type(content_type):
            logger.warning("Invalid Content-Type", extra={"content_type": content_type})
            return self._error_response(
                status_code=415,
                error_type="unsupported-media-type",
                location="header",
                name="Content-Type",
                description=f"Unsupported Content-Type: {content_type}",
            )
        return None

    def _is_valid_content_type(self, content_type: str) -> bool:
        valid_types = ["application/json", "application/x-www-form-urlencoded", "text/plain"]
        content_type_lower = content_type.lower().split(";")[0].strip()
        return content_type_lower in valid_types

    def _extract_bearer_token(self, auth_header: str) -> str | None:
        match = BEARER_TOKEN_PATTERN.match(auth_header)
        if not match:
            return None
        return match.group(1)

    def _is_valid_client_state(self, client_state: str) -> bool:
        return bool(CLIENT_STATE_PATTERN.match(client_state))

    def _error_response(
        self,
        status_code: int,
        error_type: str,
        location: str,
        name: str,
        description: str,
        log_level: str = "warning",
        **extra_log_fields,
    ) -> Response:
        log_extra = {
            "status_code": status_code,
            "error_type": error_type,
            "location": location,
            "field": name,
            "description": description,
            **extra_log_fields,
        }

        log_message = f"Token request failed: {description}"
        if log_level == "error":
            logger.error(log_message, extra=log_extra)
        elif log_level == "exception":
            logger.exception(log_message, extra=log_extra)
        else:
            logger.warning(log_message, extra=log_extra)

        body = {
            "status": error_type,
            "errors": [{"location": location, "name": name, "description": description}],
        }
        return Response(
            status_code=status_code,
            content_type="application/json",
            body=json_dumps(body),
            headers={"X-Timestamp": str(int(time.time()))},
        )
