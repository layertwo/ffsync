from datetime import datetime, timezone


def get_weave_timestamp() -> str:
    """
    Get current server timestamp in Mozilla Weave format.

    Returns:
        String timestamp with seconds since epoch and 2 decimal places precision.
        Example: "1702345678.12"

    Requirements: 9.1, 9.2
    """
    return f"{datetime.now(timezone.utc).timestamp():.2f}"


def extract_hawk_request_params(event) -> tuple[str, str, str, int]:
    """Extract (method, path, host, port) for Hawk MAC verification.

    Uses request_context.domain_name (the custom domain) rather than
    the Host header, which may differ behind edge-optimized API Gateway.
    Appends query string to path for correct Hawk MAC computation.
    """
    method = event.http_method
    path = event.path

    query_params = event.query_string_parameters
    if query_params:
        qs = "&".join(f"{k}={v}" for k, v in query_params.items())
        path = f"{path}?{qs}"

    try:
        host = event.request_context.domain_name or "localhost"
    except KeyError, AttributeError:
        host = (event.headers or {}).get("host", "localhost")

    return method, path, host, 443
