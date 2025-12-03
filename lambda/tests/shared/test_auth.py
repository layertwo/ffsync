"""Tests for authentication module"""

import pytest

from src.shared.auth import get_user_context, validate_authentication
from src.shared.exceptions import AuthenticationException


class TestValidateAuthentication:
    """Tests for validate_authentication function"""

    def test_valid_auth_header(self):
        """Test with valid AWS4-HMAC-SHA256 authorization header"""
        event = {
            "headers": {
                "Authorization": "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20231201/us-east-1/execute-api/aws4_request"
            },
            "requestContext": {},
        }

        user_id = validate_authentication(event)

        assert user_id == "mock-user-12345"

    def test_valid_auth_header_lowercase(self):
        """Test with lowercase 'authorization' header"""
        event = {
            "headers": {
                "authorization": "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE"
            },
            "requestContext": {},
        }

        user_id = validate_authentication(event)

        assert user_id == "mock-user-12345"

    def test_missing_authorization_header(self):
        """Test that missing Authorization header raises exception"""
        event = {"headers": {}, "requestContext": {}}

        with pytest.raises(AuthenticationException) as exc_info:
            validate_authentication(event)

        assert "Missing Authorization header" in str(exc_info.value)

    def test_missing_headers_dict(self):
        """Test with missing headers dictionary"""
        event = {"requestContext": {}}

        with pytest.raises(AuthenticationException) as exc_info:
            validate_authentication(event)

        assert "Missing Authorization header" in str(exc_info.value)

    def test_invalid_authorization_scheme(self):
        """Test with invalid authorization scheme"""
        event = {
            "headers": {"Authorization": "Bearer some-jwt-token"},
            "requestContext": {},
        }

        with pytest.raises(AuthenticationException) as exc_info:
            validate_authentication(event)

        assert "Invalid authorization scheme" in str(exc_info.value)

    def test_empty_authorization_header(self):
        """Test with empty authorization header"""
        event = {"headers": {"Authorization": ""}, "requestContext": {}}

        with pytest.raises(AuthenticationException) as exc_info:
            validate_authentication(event)

        assert "Missing Authorization header" in str(exc_info.value)

    def test_authorization_header_wrong_prefix(self):
        """Test with authorization header that doesn't start with AWS4-HMAC-SHA256"""
        event = {
            "headers": {"Authorization": "AWS4-SHA256 Credential=..."},
            "requestContext": {},
        }

        with pytest.raises(AuthenticationException) as exc_info:
            validate_authentication(event)

        assert "Invalid authorization scheme" in str(exc_info.value)


class TestGetUserContext:
    """Tests for get_user_context function"""

    def test_successful_user_context(self):
        """Test successful user context retrieval"""
        event = {
            "headers": {
                "Authorization": "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE"
            },
            "requestContext": {},
        }

        context = get_user_context(event)

        assert context["user_id"] == "mock-user-12345"
        assert context["authenticated"] is True

    def test_user_context_with_invalid_auth(self):
        """Test that get_user_context raises exception with invalid auth"""
        event = {"headers": {}, "requestContext": {}}

        with pytest.raises(AuthenticationException):
            get_user_context(event)

    def test_user_context_preserves_exception_message(self):
        """Test that authentication exceptions are properly propagated"""
        event = {
            "headers": {"Authorization": "Basic dXNlcjpwYXNz"},
            "requestContext": {},
        }

        with pytest.raises(AuthenticationException) as exc_info:
            get_user_context(event)

        assert "Invalid authorization scheme" in str(exc_info.value)
