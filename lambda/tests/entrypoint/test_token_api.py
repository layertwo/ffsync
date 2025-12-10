"""Tests for Token API lambda entrypoint"""

import json

import pytest

from src.entrypoint import token_api_handler
from src.services.api_router import ApiRouter
from src.services.oidc_validator import OIDCValidator
from src.services.token_generator import TokenGenerator


@pytest.fixture
def token_request_event():
    """Sample token request event"""
    return {
        "httpMethod": "POST",
        "path": "/1.0/sync/1.5",
        "headers": {
            "authorization": "Bearer valid-oidc-token",
            "content-type": "application/json",
        },
        "body": None,
        "queryStringParameters": None,
        "requestContext": {"requestId": "test-request-id"},
    }


class TestTokenApiAuthErrors:
    """Tests for authentication error handling - these don't need OIDC validation"""

    def test_missing_auth_header_returns_401(
        self, mock_service_provider, secretsmanager_stubber, oidc_secret_arn, sample_lambda_context
    ):
        """Test request without Authorization header returns 401"""
        secretsmanager_stubber.add_response(
            "get_secret_value",
            {
                "SecretString": json.dumps(
                    {"provider_url": "https://auth.example.com", "client_id": "test-client-id"}
                )
            },
            {"SecretId": oidc_secret_arn},
        )
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {},
            "body": None,
            "queryStringParameters": None,
            "requestContext": {"requestId": "test-request-id"},
        }
        result = token_api_handler(event, sample_lambda_context, mock_service_provider)
        assert result["statusCode"] == 401

    def test_missing_auth_header_error_format(
        self, mock_service_provider, secretsmanager_stubber, oidc_secret_arn, sample_lambda_context
    ):
        """Test missing auth header returns proper error format"""
        secretsmanager_stubber.add_response(
            "get_secret_value",
            {
                "SecretString": json.dumps(
                    {"provider_url": "https://auth.example.com", "client_id": "test-client-id"}
                )
            },
            {"SecretId": oidc_secret_arn},
        )
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {},
            "body": None,
            "queryStringParameters": None,
            "requestContext": {"requestId": "test-request-id"},
        }
        result = token_api_handler(event, sample_lambda_context, mock_service_provider)
        body = json.loads(result["body"])
        assert body["status"] == "invalid-credentials"
        assert len(body["errors"]) == 1
        assert body["errors"][0]["name"] == "Authorization"
        assert body["errors"][0]["location"] == "header"

    def test_malformed_auth_header_returns_400(
        self, mock_service_provider, secretsmanager_stubber, oidc_secret_arn, sample_lambda_context
    ):
        """Test request with malformed Authorization header returns 400"""
        secretsmanager_stubber.add_response(
            "get_secret_value",
            {
                "SecretString": json.dumps(
                    {"provider_url": "https://auth.example.com", "client_id": "test-client-id"}
                )
            },
            {"SecretId": oidc_secret_arn},
        )
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {"authorization": "InvalidFormat token"},
            "body": None,
            "queryStringParameters": None,
            "requestContext": {"requestId": "test-request-id"},
        }
        result = token_api_handler(event, sample_lambda_context, mock_service_provider)
        assert result["statusCode"] == 400

    def test_malformed_auth_header_error_format(
        self, mock_service_provider, secretsmanager_stubber, oidc_secret_arn, sample_lambda_context
    ):
        """Test malformed auth header returns proper error format"""
        secretsmanager_stubber.add_response(
            "get_secret_value",
            {
                "SecretString": json.dumps(
                    {"provider_url": "https://auth.example.com", "client_id": "test-client-id"}
                )
            },
            {"SecretId": oidc_secret_arn},
        )
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {"authorization": "InvalidFormat token"},
            "body": None,
            "queryStringParameters": None,
            "requestContext": {"requestId": "test-request-id"},
        }
        result = token_api_handler(event, sample_lambda_context, mock_service_provider)
        body = json.loads(result["body"])
        assert body["status"] == "invalid-request"


class TestTokenApiValidationErrors:
    """Tests for request validation error handling"""

    def test_invalid_content_type_returns_415(
        self, mock_service_provider, secretsmanager_stubber, oidc_secret_arn, sample_lambda_context
    ):
        """Test request with invalid Content-Type returns 415"""
        secretsmanager_stubber.add_response(
            "get_secret_value",
            {
                "SecretString": json.dumps(
                    {"provider_url": "https://auth.example.com", "client_id": "test-client-id"}
                )
            },
            {"SecretId": oidc_secret_arn},
        )
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {
                "authorization": "Bearer valid-token",
                "content-type": "text/xml",
            },
            "body": "some body content",
            "queryStringParameters": None,
            "requestContext": {"requestId": "test-request-id"},
        }
        result = token_api_handler(event, sample_lambda_context, mock_service_provider)
        assert result["statusCode"] == 415

    def test_invalid_content_type_error_format(
        self, mock_service_provider, secretsmanager_stubber, oidc_secret_arn, sample_lambda_context
    ):
        """Test invalid content type returns proper error format"""
        secretsmanager_stubber.add_response(
            "get_secret_value",
            {
                "SecretString": json.dumps(
                    {"provider_url": "https://auth.example.com", "client_id": "test-client-id"}
                )
            },
            {"SecretId": oidc_secret_arn},
        )
        event = {
            "httpMethod": "POST",
            "path": "/1.0/sync/1.5",
            "headers": {
                "authorization": "Bearer valid-token",
                "content-type": "text/xml",
            },
            "body": "some body content",
            "queryStringParameters": None,
            "requestContext": {"requestId": "test-request-id"},
        }
        result = token_api_handler(event, sample_lambda_context, mock_service_provider)
        body = json.loads(result["body"])
        assert body["status"] == "unsupported-media-type"


class TestServiceProviderTokenApiProperties:
    """Tests for ServiceProvider token API property initialization"""

    def test_oidc_config_fetches_from_secrets_manager(
        self, mock_service_provider, secretsmanager_stubber, oidc_secret_arn
    ):
        """Test oidc_config fetches and parses secret from Secrets Manager"""
        secretsmanager_stubber.add_response(
            "get_secret_value",
            {
                "SecretString": json.dumps(
                    {"provider_url": "https://auth.example.com", "client_id": "test-client-id"}
                )
            },
            {"SecretId": oidc_secret_arn},
        )
        config = mock_service_provider.oidc_config

        assert config["provider_url"] == "https://auth.example.com"
        assert config["client_id"] == "test-client-id"

    def test_oidc_validator_uses_oidc_config(
        self, mock_service_provider, secretsmanager_stubber, oidc_secret_arn
    ):
        """Test oidc_validator is initialized with config from Secrets Manager"""

        secretsmanager_stubber.add_response(
            "get_secret_value",
            {
                "SecretString": json.dumps(
                    {"provider_url": "https://auth.example.com", "client_id": "test-client-id"}
                )
            },
            {"SecretId": oidc_secret_arn},
        )
        validator = mock_service_provider.oidc_validator

        assert isinstance(validator, OIDCValidator)
        assert validator.provider_url == "https://auth.example.com"
        assert validator.client_id == "test-client-id"

    def test_token_api_router_creates_router_with_request_route(
        self, mock_service_provider, secretsmanager_stubber, oidc_secret_arn
    ):
        """Test token_api_router creates ApiRouter with RequestTokenRoute"""

        secretsmanager_stubber.add_response(
            "get_secret_value",
            {
                "SecretString": json.dumps(
                    {"provider_url": "https://auth.example.com", "client_id": "test-client-id"}
                )
            },
            {"SecretId": oidc_secret_arn},
        )
        router = mock_service_provider.token_api_router

        assert isinstance(router, ApiRouter)
        assert len(router._routes) == 1
