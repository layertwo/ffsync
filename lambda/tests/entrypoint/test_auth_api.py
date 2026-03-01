"""Tests for Auth API lambda entrypoint"""

import json

from src.entrypoint import auth_api_handler
from src.services.api_router import ApiRouter


class TestAuthApiErrors:
    """Tests for auth API error handling"""

    def test_unknown_route_returns_404(self, mock_service_provider, sample_lambda_context):
        """Test request to unknown path returns 404"""
        event = {
            "httpMethod": "GET",
            "path": "/v1/nonexistent",
            "headers": {},
            "body": None,
            "queryStringParameters": None,
            "requestContext": {"requestId": "test-request-id"},
        }
        result = auth_api_handler(event, sample_lambda_context, mock_service_provider)
        assert result["statusCode"] == 404

    def test_session_route_without_auth_returns_401(
        self, mock_service_provider, sample_lambda_context
    ):
        """Test session-protected route without auth header returns 401 via exception handler.

        The HawkAuthMiddleware raises HawkAuthenticationError which is caught
        by the auth_exception_handlers and returns a 401 with errno 110.
        """
        event = {
            "httpMethod": "GET",
            "path": "/v1/session/status",
            "headers": {},
            "body": None,
            "queryStringParameters": None,
            "requestContext": {
                "requestId": "test-request-id",
                "domainName": "auth.sync.example.com",
            },
        }
        result = auth_api_handler(event, sample_lambda_context, mock_service_provider)
        assert result["statusCode"] == 401
        body = json.loads(result["body"])
        assert body["errno"] == 110


class TestServiceProviderAuthApiProperties:
    """Tests for ServiceProvider auth API property initialization"""

    def test_auth_api_router_creates_router_with_routes(self, mock_service_provider):
        """Test auth_api_router creates ApiRouter with auth routes"""
        router = mock_service_provider.auth_api_router

        assert isinstance(router, ApiRouter)
        assert len(router._routes) > 1
