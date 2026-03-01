"""Request logging middleware.

Logs request and response information with structured JSON format.
"""

import time

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler, NextMiddleware

logger = Logger(service="storage-server")


class RequestLoggingMiddleware(BaseMiddlewareHandler):

    def handler(self, app: APIGatewayRestResolver, next_middleware: NextMiddleware) -> Response:
        event = app.current_event
        method = event.get("httpMethod", "UNKNOWN")
        path = event.get("path", "UNKNOWN")

        user_id = event.get("requestContext", {}).get("hawk_uid", "anonymous")  # type: ignore

        logger.info(
            "Request received",
            extra={"method": method, "path": path, "user_id": user_id},
        )

        start_time = time.time()

        try:
            response = next_middleware(app)

            duration_ms = round((time.time() - start_time) * 1000, 2)
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
            duration_ms = round((time.time() - start_time) * 1000, 2)
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
                exc_info=True,
            )
            raise
