from typing import Any, Dict, Optional

from src.shared.exceptions import AuthenticationException


def validate_authentication(event: Dict[str, Any]) -> Optional[str]:
    """
    Validate AWS SigV4 authentication from API Gateway event

    Args:
        event: API Gateway event containing request context

    Returns:
        user_id: Authenticated user identifier

    Raises:
        AuthenticationException: If authentication is invalid or missing
    """
    # TODO: Implement proper SigV4 authentication validation
    # For now, this is a placeholder that would need to:
    # 1. Extract authorization headers from event
    # 2. Validate SigV4 signature
    # 3. Extract user identity from credentials
    # 4. Return authenticated user ID

    # Check if request context exists (from API Gateway)
    request_context = event.get("requestContext", {})

    # In a real implementation, this would validate the SigV4 signature
    # For development/testing, we'll accept any request with an Authorization header
    headers = event.get("headers", {})
    auth_header = headers.get("Authorization") or headers.get("authorization")

    if not auth_header:
        raise AuthenticationException("Missing Authorization header")

    # TODO: Replace with actual SigV4 validation logic
    # This is a placeholder that extracts a mock user ID
    if not auth_header.startswith("AWS4-HMAC-SHA256"):
        raise AuthenticationException("Invalid authorization scheme")

    # Mock user ID extraction - in real implementation this would come from
    # validated credentials or JWT token
    user_id = "mock-user-12345"

    return user_id


def get_user_context(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get authenticated user context from the request

    Args:
        event: API Gateway event

    Returns:
        User context dictionary with user_id and other metadata
    """
    user_id = validate_authentication(event)

    return {"user_id": user_id, "authenticated": True}
