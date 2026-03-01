"""Tests for Auth API lambda entrypoint"""

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


class TestServiceProviderAuthApiProperties:
    """Tests for ServiceProvider auth API property initialization"""

    def test_auth_api_router_creates_router_with_routes(self, mock_service_provider):
        """Test auth_api_router creates ApiRouter with auth routes"""
        router = mock_service_provider.auth_api_router

        assert isinstance(router, ApiRouter)
        assert len(router._routes) > 1
