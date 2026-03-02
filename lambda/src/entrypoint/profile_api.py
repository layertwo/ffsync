from aws_lambda_powertools.utilities.typing import LambdaContext

from src.environment.service_provider import ServiceProvider, lambda_entrypoint


@lambda_entrypoint
def lambda_handler(event: dict, context: LambdaContext, service_provider: ServiceProvider) -> dict:
    return service_provider.profile_api_router.handler(event, context)
