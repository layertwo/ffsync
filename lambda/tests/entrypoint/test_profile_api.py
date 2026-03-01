"""Tests for Profile API lambda entrypoint"""

import json

from src.entrypoint import profile_api_handler
from src.services.api_router import ApiRouter


class TestProfileApiAuthErrors:
    """Tests for authentication error handling"""

    def test_missing_auth_header_returns_401(self, mock_service_provider, sample_lambda_context):
        """Test request without Authorization header returns 401"""
        event = {
            "httpMethod": "GET",
            "path": "/v1/profile",
            "headers": {},
            "body": None,
            "queryStringParameters": None,
            "requestContext": {"requestId": "test-request-id"},
        }
        result = profile_api_handler(event, sample_lambda_context, mock_service_provider)
        assert result["statusCode"] == 401

    def test_missing_auth_header_error_format(self, mock_service_provider, sample_lambda_context):
        """Test missing auth header returns proper error body"""
        event = {
            "httpMethod": "GET",
            "path": "/v1/profile",
            "headers": {},
            "body": None,
            "queryStringParameters": None,
            "requestContext": {"requestId": "test-request-id"},
        }
        result = profile_api_handler(event, sample_lambda_context, mock_service_provider)
        body = json.loads(result["body"])
        assert body["errno"] == 110


class TestServiceProviderProfileApiProperties:
    """Tests for ServiceProvider profile API property initialization"""

    def test_profile_api_router_creates_router_with_routes(self, mock_service_provider):
        """Test profile_api_router creates ApiRouter with profile route"""
        router = mock_service_provider.profile_api_router

        assert isinstance(router, ApiRouter)
        assert len(router._routes) == 1
