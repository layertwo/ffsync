"""Weave response headers: X-Last-Modified (storage only) and X-Weave-Timestamp.

Also applied to exception-handler responses, which skip the middleware chain.
"""

from typing import Optional

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler, NextMiddleware

from src.shared.models import get_current_timestamp


def apply_weave_headers(response: Response, *, ensure_last_modified: bool = False) -> Response:
    """Set X-Weave-Timestamp, plus X-Last-Modified when the caller owns it (storage)."""
    now = get_current_timestamp()
    last_modified: Optional[str] = _header_value(response, "X-Last-Modified")

    if last_modified is None and ensure_last_modified:
        last_modified = f"{now:.2f}"
        response.headers["X-Last-Modified"] = last_modified

    # Every producer writes a numeric string, so parsing cannot fail here.
    weave_ts = max(float(last_modified), now) if last_modified is not None else now
    response.headers["X-Weave-Timestamp"] = f"{weave_ts:.2f}"
    return response


def _header_value(response: Response, name: str) -> Optional[str]:
    value = response.headers.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


class WeaveTimestampMiddleware(BaseMiddlewareHandler):
    """Adds X-Weave-Timestamp to responses that do pass through the router."""

    def handler(self, app: APIGatewayRestResolver, next_middleware: NextMiddleware) -> Response:
        return apply_weave_headers(next_middleware(app))
