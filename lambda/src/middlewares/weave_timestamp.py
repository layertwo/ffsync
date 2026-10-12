"""Weave response headers.

The storage API sets two, and Mozilla's server does the same in two wrappers:

- ``transaction.rs`` ensures ``X-Last-Modified`` (from the resource timestamp)
  unless the handler already set one.
- ``middleware/weave.rs`` then sets ``X-Weave-Timestamp`` to the later of that
  and the server's clock, so the weave timestamp is never behind the resource's
  modification time. The spec wants it "returned with all responses".

Exception-handler responses never pass through the middleware chain, so the same
helper is applied to them directly (see ``ApiRouter._register_exception_handlers``).
"""

from typing import Optional

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.middlewares import BaseMiddlewareHandler, NextMiddleware

from src.shared.models import get_current_timestamp


def apply_weave_headers(response: Response, *, ensure_last_modified: bool = False) -> Response:
    """Set X-Weave-Timestamp, and X-Last-Modified when the caller owns it.

    ``ensure_last_modified`` is for the storage API only: the auth, token and
    profile APIs send X-Weave-Timestamp but have no resource timestamp to
    report.
    """
    now = get_current_timestamp()
    last_modified: Optional[str] = _header_value(response, "X-Last-Modified")

    if last_modified is None and ensure_last_modified:
        last_modified = f"{now:.2f}"
        response.headers["X-Last-Modified"] = last_modified

    # Every producer of X-Last-Modified writes a numeric string (str(round(...)),
    # "0.00" or f"{ts:.2f}"), so parsing it cannot fail here: a malformed one is a
    # bug to fix rather than a case to tolerate.
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
