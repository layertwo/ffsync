from src.environment.service_provider import ServiceProvider


def lambda_handler(event, context, service_provider=None) -> dict:
    """
    Lambda handler with dependency injection for testing.

    Args:
        event: Lambda event
        context: Lambda context
        service_provider: Optional ServiceProvider for testing (defaults to None)

    Returns:
        API response dict
    """
    if service_provider is None:
        service_provider = ServiceProvider()
    return service_provider.api_router.handler(event, context)
