from typing import Optional

from aws_lambda_powertools.utilities.typing import LambdaContext

from src.environment.service_provider import ServiceProvider


def lambda_handler(
    event: dict, context: LambdaContext, service_provider: Optional[ServiceProvider] = None
) -> dict:
    """
    Auth Service API Lambda handler.

    Handles all FxA-compatible auth endpoints:
    - GET /1.0/sync/1.5 (sync token issuance)
    - POST /v1/account/create, /v1/account/login, /v1/account/keys, etc.
    - POST /v1/oauth/authorization, /v1/oauth/token, /v1/oauth/destroy
    - GET /v1/session/status, POST /v1/session/destroy
    - GET /.well-known/openid-configuration, /v1/jwks

    Args:
        event: Lambda event from API Gateway
        context: Lambda context
        service_provider: Optional ServiceProvider for dependency injection

    Returns:
        API Gateway proxy response dict
    """
    if service_provider is None:  # pragma: nocover
        service_provider = ServiceProvider()
    return service_provider.auth_api_router.handler(event, context)
