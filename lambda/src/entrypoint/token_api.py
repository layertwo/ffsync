from typing import Optional

from aws_lambda_powertools.utilities.typing import LambdaContext

from src.environment.service_provider import ServiceProvider


def lambda_handler(
    event: dict, context: LambdaContext, service_provider: Optional[ServiceProvider] = None
) -> dict:
    """
    Token Service API Lambda handler.

    Handles POST /1.0/sync/1.5 requests to exchange OIDC tokens
    for Firefox Sync HAWK credentials.

    Request flow:
    1. Validate request (HTTP method, path, headers)
    2. Extract and validate Authorization header (Bearer token)
    3. Validate OIDC token with configured provider
    4. Get or create user record in DynamoDB
    5. Generate HAWK credentials and token response
    6. Return JSON response with token details

    Args:
        event: Lambda event from API Gateway
        context: Lambda context
        service_provider: Optional ServiceProvider for dependency injection

    Returns:
        API Gateway proxy response dict with token or error
    """
    if service_provider is None:  # pragma: nocover
        service_provider = ServiceProvider()
    return service_provider.token_api_router.handler(event, context)
