from src.environment.service_provider import ServiceProvider


def lambda_handler(event, context) -> dict:
    service_provider = ServiceProvider()
    return service_provider.api_router.handler(event, context)
