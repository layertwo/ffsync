from typing import Optional

from aws_lambda_powertools.utilities.typing import LambdaContext

from src.environment.service_provider import ServiceProvider


def lambda_handler(
    event: dict, context: LambdaContext, service_provider: Optional[ServiceProvider] = None
) -> dict:
    """
    Profile API Lambda handler.

    Handles GET /v1/profile requests to return user profile info
    authenticated via OAuth Bearer tokens.

    Args:
        event: Lambda event from API Gateway
        context: Lambda context
        service_provider: Optional ServiceProvider for dependency injection

    Returns:
        API Gateway proxy response dict with profile or error
    """
    if service_provider is None:  # pragma: nocover
        service_provider = ServiceProvider()
    return service_provider.profile_api_router.handler(event, context)
