"""
HAWK Lambda Authorizer Entry Point

API Gateway REQUEST authorizer for validating HAWK authentication.
"""

import time
from typing import Any, Dict, Optional

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes.api_gateway_authorizer_event import (
    APIGatewayAuthorizerRequestEvent,
    APIGatewayAuthorizerResponse,
)
from aws_lambda_powertools.utilities.typing import LambdaContext

from src.environment.service_provider import ServiceProvider
from src.shared.exceptions import (
    AuthenticationException,
    ExpiredHawkTokenException,
    InvalidGenerationException,
    InvalidHawkHeaderException,
    InvalidHawkSignatureException,
)

logger = Logger(service="hawk-authorizer")


def lambda_handler(
    event: dict,
    context: LambdaContext,
    service_provider: Optional[ServiceProvider] = None,
) -> Dict[str, Any]:
    """
    Lambda handler for API Gateway REQUEST authorizer.

    Uses AWS Lambda Powertools data classes for type-safe event parsing.

    Args:
        event: Raw event dict from API Gateway (will be parsed into APIGatewayAuthorizerRequestEvent)
        context: Lambda context object
        service_provider: Optional ServiceProvider for dependency injection

    Returns:
        IAM policy document with context:
            {
                "principalId": "user_id",
                "policyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Action": "execute-api:Invoke",
                        "Effect": "Allow",
                        "Resource": "arn:aws:execute-api:..."
                    }]
                },
                "context": {
                    "user_id": "abc123",
                    "hawk_id": "base64_encoded_id",
                    "authenticated_at": "1702345678.12"
                }
            }

    Raises:
        Exception: With message "Unauthorized" to return 401 instead of 403
    """
    if service_provider is None:  # pragma: nocover
        service_provider = ServiceProvider()

    authorizer_event = APIGatewayAuthorizerRequestEvent(event)

    try:
        # Extract Authorization header (case-insensitive via Powertools)
        authorization_header = authorizer_event.headers.get("Authorization")

        if not authorization_header:
            logger.warning("Missing Authorization header")
            raise AuthenticationException("Missing Authorization header")

        # Extract request details using typed properties
        method = authorizer_event.http_method
        # Hawk MAC must be computed over the full resource URI including query string
        path = authorizer_event.path
        query_params = (event.get("queryStringParameters") or {}) or None
        if query_params:
            qs = "&".join(f"{k}={v}" for k, v in query_params.items())
            path = f"{path}?{qs}"
        domain_name = (
            authorizer_event.request_context.domain_name if authorizer_event.request_context else ""
        )

        # Parse host and port from domain name
        # API Gateway uses standard ports (443 for HTTPS)
        host = domain_name or ""
        port = 443

        # Get HAWK service from ServiceProvider
        hawk_service = service_provider.hawk_service

        # Validate HAWK credentials
        credentials = hawk_service.validate(authorization_header, method, path, host, port)

        # Parse ARN for policy generation
        arn = authorizer_event.parsed_arn

        # Generate Allow policy with user context using Powertools
        policy = APIGatewayAuthorizerResponse(
            principal_id=credentials.user_id,
            region=arn.region,
            aws_account_id=arn.aws_account_id,
            api_id=arn.api_id,
            stage=arn.stage,
            context={
                "user_id": credentials.user_id,
                "hawk_id": credentials.hawk_id,
                "generation": str(credentials.generation),
                "authenticated_at": str(round(time.time(), 2)),
            },
            usage_identifier_key=credentials.user_id,
        )
        policy.allow_all_routes()

        logger.info(
            f"HAWK authentication successful for user {credentials.user_id}",
            extra={"user_id": credentials.user_id},
        )

        return policy.asdict()

    except (
        InvalidHawkHeaderException,
        InvalidHawkSignatureException,
        ExpiredHawkTokenException,
        InvalidGenerationException,
        AuthenticationException,
    ) as e:
        # Log authentication failure
        logger.warning(f"HAWK authentication failed: {e}")

        # API Gateway returns 403 for Deny policies
        # To return 401, we must raise an exception with message "Unauthorized"
        raise Exception("Unauthorized")

    except Exception as e:
        # Log unexpected errors
        logger.error(f"Unexpected error in HAWK authorizer: {e}", exc_info=True)

        # Return 401 for any unexpected errors
        raise Exception("Unauthorized")
