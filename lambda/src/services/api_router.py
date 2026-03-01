import time
from typing import Any, Sequence

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, CORSConfig, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler, NextMiddleware
from aws_lambda_powertools.utilities.typing import LambdaContext

from src.services.hawk_service import HawkService
from src.services.token_generator import TokenGenerator
from src.shared.base_route import BaseRoute
from src.shared.utils import get_weave_timestamp

logger = Logger(service="storage-server")


class StorageHawkMiddleware(BaseMiddlewareHandler):
    """
    Middleware that validates Hawk authentication for storage API requests.

    Replaces the separate Lambda authorizer with in-process Hawk validation,
    injecting the same authorizer context shape into the event so downstream
    middleware (UidValidationMiddleware) and route handlers work unchanged.
    """

    def __init__(self, hawk_service: HawkService):
        super().__init__()
        self._hawk_service = hawk_service

    def handler(self, app: APIGatewayRestResolver, next_middleware: NextMiddleware) -> Response:
        event = app.current_event

        # Extract Authorization header
        headers = event.headers or {}
        auth_header = headers.get("Authorization") or headers.get("authorization")
        if not auth_header:
            return Response(
                status_code=401,
                content_type="application/json",
                body='{"error": "Unauthorized"}',
            )

        # Extract request details for Hawk MAC validation
        method = event.http_method
        path = event.path
        query_params = event.query_string_parameters
        if query_params:
            qs = "&".join(f"{k}={v}" for k, v in query_params.items())
            path = f"{path}?{qs}"

        # Parse host from request context or headers
        try:
            host = event.request_context.domain_name
        except (AttributeError, KeyError):
            host = headers.get("host", "localhost")
        port = 443

        try:
            credentials = self._hawk_service.validate(auth_header, method, path, host, port)
        except Exception:
            return Response(
                status_code=401,
                content_type="application/json",
                body='{"error": "Unauthorized"}',
            )

        # Inject authorizer context — same shape as the Lambda authorizer produced
        event["requestContext"]["authorizer"] = {
            "user_id": credentials.user_id,
            "hawk_id": credentials.hawk_id,
            "generation": str(credentials.generation),
            "authenticated_at": str(round(time.time(), 2)),
        }

        return next_middleware(app)


class RequestLoggingMiddleware(BaseMiddlewareHandler):
    """
    Middleware that logs request and response information.

    Requirements: 14.1-14.4
    - Logs request method, path, and user_id
    - Logs response status code and duration
    - Uses structured logging with JSON format
    - Never logs BSO payloads or sensitive user data
    """

    def handler(self, app: APIGatewayRestResolver, next_middleware: NextMiddleware) -> Response:
        # Extract request information
        event = app.current_event
        method = event.get("httpMethod", "UNKNOWN")
        path = event.get("path", "UNKNOWN")

        # Extract user_id from authorizer context with proper type handling
        user_id = event.get("requestContext", {}).get("authorizer", {}).get("user_id", "anonymous")  # type: ignore

        # Log request received
        logger.info(
            "Request received",
            extra={
                "method": method,
                "path": path,
                "user_id": user_id,
            },
        )

        # Track request start time
        start_time = time.time()

        try:
            # Call the next middleware/handler in the chain
            response = next_middleware(app)

            # Calculate duration
            duration_ms = round((time.time() - start_time) * 1000, 2)

            # Log request completed
            logger.info(
                "Request completed",
                extra={
                    "method": method,
                    "path": path,
                    "user_id": user_id,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )

            return response

        except Exception as e:
            # Calculate duration
            duration_ms = round((time.time() - start_time) * 1000, 2)

            # Log error with details (Requirements 14.2)
            logger.error(
                "Request failed",
                extra={
                    "method": method,
                    "path": path,
                    "user_id": user_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "duration_ms": duration_ms,
                },
                exc_info=True,  # Include stack trace
            )

            # Re-raise the exception to be handled by the framework
            raise


class WeaveTimestampMiddleware(BaseMiddlewareHandler):
    """
    Middleware that adds X-Weave-Timestamp header to all responses.

    Requirements: 9.1-9.4
    """

    def handler(self, app: APIGatewayRestResolver, next_middleware: NextMiddleware) -> Response:
        # Call the next middleware/handler in the chain
        response = next_middleware(app)

        # Add X-Weave-Timestamp header to the response
        response.headers["X-Weave-Timestamp"] = get_weave_timestamp()

        return response


class UidValidationMiddleware(BaseMiddlewareHandler):
    """
    Middleware that validates the URL uid against the Hawk-authenticated user.

    Computes the expected uid from user_id + generation in the authorizer context
    and compares it against the uid path parameter. Returns 403 on mismatch.
    """

    def handler(self, app: APIGatewayRestResolver, next_middleware: NextMiddleware) -> Response:
        event = app.current_event
        authorizer = event.get("requestContext", {}).get("authorizer", {})  # type: ignore
        path_params = event.get("pathParameters") or {}

        path_uid = path_params.get("uid")
        user_id = authorizer.get("user_id")
        generation_str = authorizer.get("generation")

        if path_uid and user_id and generation_str is not None:
            expected_uid = str(TokenGenerator.generate_uid(user_id, int(generation_str)))
            if path_uid != expected_uid:
                return Response(
                    status_code=403,
                    content_type="application/json",
                    body='{"error": "uid mismatch"}',
                )

        return next_middleware(app)


class ApiRouter:
    def __init__(
        self,
        routes: list[BaseRoute],
        middlewares: Sequence[BaseMiddlewareHandler[Any]],
        cors: CORSConfig | None = None,
    ):
        self.app = APIGatewayRestResolver(cors=cors)
        self._routes = routes
        self._middlewares = middlewares

        self._register_middleware()
        self._register_routes()

    def _register_middleware(self):
        """Register middleware handlers"""
        # Cast to list of callables for mypy compatibility
        self.app.use(middlewares=self._middlewares)  # type: ignore

    def _register_routes(self):
        """Register routes by calling each route's bind method"""
        for route in self._routes:
            route.bind(self.app)

    def handler(self, event: dict, context: LambdaContext):
        """Main Lambda handler entry point"""
        return self.app.resolve(event=event, context=context)
