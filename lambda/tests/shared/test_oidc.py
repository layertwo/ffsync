"""Tests for OIDC-related models"""

import json

import pytest

from src.shared.oidc import ErrorDetail, OIDCProviderConfig, OIDCTokenClaims


class TestOIDCTokenClaims:
    """Tests for OIDCTokenClaims model"""

    def test_creation_with_all_fields(self):
        """Test creating OIDCTokenClaims with all fields including email"""
        claims = OIDCTokenClaims(
            sub="user123",
            iss="https://auth.example.com",
            aud="client-id-123",
            exp=1234567890,
            iat=1234567800,
            email="user@example.com",
        )

        assert claims.sub == "user123"
        assert claims.iss == "https://auth.example.com"
        assert claims.aud == "client-id-123"
        assert claims.exp == 1234567890
        assert claims.iat == 1234567800
        assert claims.email == "user@example.com"

    def test_creation_without_email(self):
        """Test creating OIDCTokenClaims without optional email field"""
        claims = OIDCTokenClaims(
            sub="user456",
            iss="https://auth.example.com",
            aud="client-id-456",
            exp=1234567890,
            iat=1234567800,
        )

        assert claims.sub == "user456"
        assert claims.email is None

    def test_to_json(self):
        """Test serialization to JSON"""
        claims = OIDCTokenClaims(
            sub="user789",
            iss="https://auth.example.com",
            aud="client-id-789",
            exp=1234567890,
            iat=1234567800,
            email="user789@example.com",
        )

        json_str = claims.to_json()
        data = json.loads(json_str)

        assert data["sub"] == "user789"
        assert data["iss"] == "https://auth.example.com"
        assert data["aud"] == "client-id-789"
        assert data["exp"] == 1234567890
        assert data["iat"] == 1234567800
        assert data["email"] == "user789@example.com"

    def test_from_json(self):
        """Test deserialization from JSON"""
        json_str = '{"sub": "user999", "iss": "https://auth.example.com", "aud": "client-id", "exp": 1234567890, "iat": 1234567800, "email": "user999@example.com"}'
        claims = OIDCTokenClaims.from_json(json_str)

        assert claims.sub == "user999"
        assert claims.iss == "https://auth.example.com"
        assert claims.email == "user999@example.com"

    def test_round_trip_serialization(self):
        """Test that serialization and deserialization are inverses"""
        original = OIDCTokenClaims(
            sub="roundtrip",
            iss="https://auth.example.com",
            aud="client-id",
            exp=1234567890,
            iat=1234567800,
            email="roundtrip@example.com",
        )

        json_str = original.to_json()
        restored = OIDCTokenClaims.from_json(json_str)

        assert restored.sub == original.sub
        assert restored.iss == original.iss
        assert restored.aud == original.aud
        assert restored.exp == original.exp
        assert restored.iat == original.iat
        assert restored.email == original.email

    def test_exp_greater_than_iat(self):
        """Test that expiry is after issued at time"""
        claims = OIDCTokenClaims(
            sub="user",
            iss="https://auth.example.com",
            aud="client-id",
            exp=1234567890,
            iat=1234567800,
        )

        assert claims.exp > claims.iat

    def test_to_dict(self):
        """Test conversion to dictionary"""
        claims = OIDCTokenClaims(
            sub="dictuser",
            iss="https://auth.example.com",
            aud="client-id",
            exp=1234567890,
            iat=1234567800,
        )

        data = claims.to_dict()

        assert isinstance(data, dict)
        assert data["sub"] == "dictuser"
        assert data["iss"] == "https://auth.example.com"


class TestOIDCProviderConfig:
    """Tests for OIDCProviderConfig model"""

    def test_creation_with_all_fields(self):
        """Test creating OIDCProviderConfig with all fields"""
        config = OIDCProviderConfig(
            issuer="https://auth.example.com",
            jwks_uri="https://auth.example.com/jwks",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            userinfo_endpoint="https://auth.example.com/userinfo",
        )

        assert config.issuer == "https://auth.example.com"
        assert config.jwks_uri == "https://auth.example.com/jwks"
        assert config.authorization_endpoint == "https://auth.example.com/authorize"
        assert config.token_endpoint == "https://auth.example.com/token"
        assert config.userinfo_endpoint == "https://auth.example.com/userinfo"

    def test_to_json(self):
        """Test serialization to JSON"""
        config = OIDCProviderConfig(
            issuer="https://auth.example.com",
            jwks_uri="https://auth.example.com/jwks",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            userinfo_endpoint="https://auth.example.com/userinfo",
        )

        json_str = config.to_json()
        data = json.loads(json_str)

        assert data["issuer"] == "https://auth.example.com"
        assert data["jwks_uri"] == "https://auth.example.com/jwks"
        assert data["authorization_endpoint"] == "https://auth.example.com/authorize"

    def test_from_json(self):
        """Test deserialization from JSON"""
        json_str = '{"issuer": "https://auth.example.com", "jwks_uri": "https://auth.example.com/jwks", "authorization_endpoint": "https://auth.example.com/authorize", "token_endpoint": "https://auth.example.com/token", "userinfo_endpoint": "https://auth.example.com/userinfo"}'
        config = OIDCProviderConfig.from_json(json_str)

        assert config.issuer == "https://auth.example.com"
        assert config.jwks_uri == "https://auth.example.com/jwks"

    def test_round_trip_serialization(self):
        """Test that serialization and deserialization are inverses"""
        original = OIDCProviderConfig(
            issuer="https://auth.example.com",
            jwks_uri="https://auth.example.com/jwks",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            userinfo_endpoint="https://auth.example.com/userinfo",
        )

        json_str = original.to_json()
        restored = OIDCProviderConfig.from_json(json_str)

        assert restored.issuer == original.issuer
        assert restored.jwks_uri == original.jwks_uri
        assert restored.authorization_endpoint == original.authorization_endpoint
        assert restored.token_endpoint == original.token_endpoint
        assert restored.userinfo_endpoint == original.userinfo_endpoint

    def test_from_dict(self):
        """Test creation from dictionary"""
        data = {
            "issuer": "https://auth.example.com",
            "jwks_uri": "https://auth.example.com/jwks",
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
            "userinfo_endpoint": "https://auth.example.com/userinfo",
        }

        config = OIDCProviderConfig.from_dict(data)

        assert config.issuer == "https://auth.example.com"
        assert config.jwks_uri == "https://auth.example.com/jwks"


class TestErrorDetail:
    """Tests for ErrorDetail model"""

    def test_creation_with_all_fields(self):
        """Test creating ErrorDetail with all fields"""
        error = ErrorDetail(
            location="header",
            name="Authorization",
            description="Missing authorization header",
        )

        assert error.location == "header"
        assert error.name == "Authorization"
        assert error.description == "Missing authorization header"

    def test_creation_with_body_location(self):
        """Test creating ErrorDetail with body location"""
        error = ErrorDetail(location="body", name="email", description="Invalid email format")

        assert error.location == "body"
        assert error.name == "email"

    def test_creation_with_query_location(self):
        """Test creating ErrorDetail with query location"""
        error = ErrorDetail(location="query", name="limit", description="Limit must be positive")

        assert error.location == "query"

    def test_to_json(self):
        """Test serialization to JSON"""
        error = ErrorDetail(
            location="header",
            name="Content-Type",
            description="Invalid content type",
        )

        json_str = error.to_json()
        data = json.loads(json_str)

        assert data["location"] == "header"
        assert data["name"] == "Content-Type"
        assert data["description"] == "Invalid content type"

    def test_from_json(self):
        """Test deserialization from JSON"""
        json_str = '{"location": "body", "name": "password", "description": "Password too short"}'
        error = ErrorDetail.from_json(json_str)

        assert error.location == "body"
        assert error.name == "password"
        assert error.description == "Password too short"

    def test_round_trip_serialization(self):
        """Test that serialization and deserialization are inverses"""
        original = ErrorDetail(
            location="query",
            name="page",
            description="Page number must be an integer",
        )

        json_str = original.to_json()
        restored = ErrorDetail.from_json(json_str)

        assert restored.location == original.location
        assert restored.name == original.name
        assert restored.description == original.description

    def test_to_dict(self):
        """Test conversion to dictionary"""
        error = ErrorDetail(location="header", name="Accept", description="Unsupported media type")

        data = error.to_dict()

        assert isinstance(data, dict)
        assert data["location"] == "header"
        assert data["name"] == "Accept"
        assert data["description"] == "Unsupported media type"

    def test_from_dict(self):
        """Test creation from dictionary"""
        data = {
            "location": "body",
            "name": "username",
            "description": "Username already exists",
        }

        error = ErrorDetail.from_dict(data)

        assert error.location == "body"
        assert error.name == "username"
        assert error.description == "Username already exists"
