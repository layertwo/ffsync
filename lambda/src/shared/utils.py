import json
from datetime import datetime, timezone
from decimal import Decimal


def datetime_encoder(dt: datetime) -> Decimal:
    """Convert datetime to Unix timestamp (Decimal) for DynamoDB serialization"""
    # Treat naive datetime as UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # pragma: nocover
    return Decimal(str(dt.timestamp()))


def datetime_decoder(timestamp: float) -> datetime:
    """Convert Unix timestamp (float/Decimal) to datetime for deserialization"""
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)


def float_to_decimal(value: float) -> Decimal:
    """Convert float to Decimal for DynamoDB serialization"""
    return Decimal(str(value))


def decimal_to_float(value: Decimal) -> float:
    """Convert Decimal to float for deserialization"""
    return float(value)


def get_weave_timestamp() -> str:
    """
    Get current server timestamp in Mozilla Weave format.

    Returns:
        String timestamp with seconds since epoch and 2 decimal places precision.
        Example: "1702345678.12"

    Requirements: 9.1, 9.2
    """
    return f"{datetime.now(timezone.utc).timestamp():.2f}"


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal objects by converting them to float"""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def json_dumps(obj, **kwargs) -> str:
    """JSON dumps wrapper that handles Decimal objects"""
    return json.dumps(obj, cls=DecimalEncoder, **kwargs)


def extract_hawk_request_params(event) -> tuple[str, str, str, str]:
    """Extract (method, path, host, port) for Hawk MAC verification.

    Uses request_context.domain_name (the custom domain) rather than
    the Host header, which may differ behind edge-optimized API Gateway.
    Appends query string to path for correct Hawk MAC computation.
    """
    from aws_lambda_powertools import Logger

    _logger = Logger(child=True)

    method = event.http_method
    path = event.path

    query_params = event.query_string_parameters
    if query_params:
        qs = "&".join(f"{k}={v}" for k, v in query_params.items())
        path = f"{path}?{qs}"

    headers = event.headers or {}
    host_header = headers.get("host", "")

    try:
        host = event.request_context.domain_name or "localhost"
    except (KeyError, AttributeError):
        host = host_header or "localhost"

    port = "443"

    _logger.debug(
        "Hawk request params",
        extra={
            "method": method,
            "path": path,
            "domain_name": host,
            "host_header": host_header,
            "port": port,
        },
    )

    return method, path, host, port
