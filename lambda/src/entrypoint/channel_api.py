"""Channel API Lambda handler for WebSocket device pairing."""

from aws_lambda_powertools.utilities.typing import LambdaContext

from src.environment.service_provider import ServiceProvider, lambda_entrypoint


@lambda_entrypoint
def lambda_handler(event: dict, context: LambdaContext, service_provider: ServiceProvider) -> dict:
    """
    Channel Service WebSocket Lambda handler.

    Handles WebSocket $connect, $disconnect, and $default routes
    for device pairing channel relay.

    Args:
        event: Lambda event from API Gateway WebSocket
        context: Lambda context
        service_provider: ServiceProvider injected by @lambda_entrypoint

    Returns:
        WebSocket response dict
    """
    return service_provider.channel_service.handle(event, context)
