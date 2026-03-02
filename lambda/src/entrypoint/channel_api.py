"""Channel API Lambda handler for WebSocket device pairing."""

from typing import Optional

from aws_lambda_powertools.utilities.typing import LambdaContext

from src.environment.service_provider import ServiceProvider


def lambda_handler(
    event: dict, context: LambdaContext, service_provider: Optional[ServiceProvider] = None
) -> dict:
    """
    Channel Service WebSocket Lambda handler.

    Handles WebSocket $connect, $disconnect, and $default routes
    for device pairing channel relay.

    Args:
        event: Lambda event from API Gateway WebSocket
        context: Lambda context
        service_provider: Optional ServiceProvider for dependency injection

    Returns:
        WebSocket response dict
    """
    if service_provider is None:  # pragma: nocover
        service_provider = ServiceProvider()
    return service_provider.channel_service.handle(event, context)
