from typing import Optional

from aws_lambda_powertools.utilities.typing import LambdaContext

from src.environment.service_provider import ServiceProvider


def lambda_handler(
    event: dict, context: LambdaContext, service_provider: Optional[ServiceProvider] = None
) -> dict:
    """
    Storage Service API Lambda handler.

    Args:
        event: Lambda event
        context: Lambda context
        service_provider: Optional ServiceProvider

    Returns:
        API response dict
    """
    if service_provider is None:  # pragma: nocover
        service_provider = ServiceProvider()
    return service_provider.storage_api_router.handler(event, context)
