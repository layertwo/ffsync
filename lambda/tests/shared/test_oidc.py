"""Tests for OIDC-related models"""

from dataclasses import asdict

from src.shared.oidc import ErrorDetail, OIDCProviderConfig, OIDCTokenClaims


class TestOIDCTokenClaims:
    """Tests for OIDCTokenClaims model"""

    def test_creation_with_all_fields(self):
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
        claims = OIDCTokenClaims(
            sub="user456",
            iss="https://auth.example.com",
            aud="client-id-456",
            exp=1234567890,
            iat=1234567800,
        )

        assert claims.sub == "user456"
        assert claims.email is None

    def test_exp_greater_than_iat(self):
        claims = OIDCTokenClaims(
            sub="user",
            iss="https://auth.example.com",
            aud="client-id",
            exp=1234567890,
            iat=1234567800,
        )

        assert claims.exp > claims.iat

    def test_asdict(self):
        claims = OIDCTokenClaims(
            sub="dictuser",
            iss="https://auth.example.com",
            aud="client-id",
            exp=1234567890,
            iat=1234567800,
        )

        data = asdict(claims)

        assert isinstance(data, dict)
        assert data["sub"] == "dictuser"
        assert data["iss"] == "https://auth.example.com"


class TestOIDCProviderConfig:
    """Tests for OIDCProviderConfig model"""

    def test_creation_with_all_fields(self):
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


class TestErrorDetail:
    """Tests for ErrorDetail model"""

    def test_creation_with_all_fields(self):
        error = ErrorDetail(
            location="header",
            name="Authorization",
            description="Missing authorization header",
        )

        assert error.location == "header"
        assert error.name == "Authorization"
        assert error.description == "Missing authorization header"

    def test_creation_with_body_location(self):
        error = ErrorDetail(location="body", name="email", description="Invalid email format")
        assert error.location == "body"
        assert error.name == "email"

    def test_creation_with_query_location(self):
        error = ErrorDetail(location="query", name="limit", description="Limit must be positive")
        assert error.location == "query"

    def test_asdict(self):
        error = ErrorDetail(location="header", name="Accept", description="Unsupported media type")

        data = asdict(error)

        assert isinstance(data, dict)
        assert data["location"] == "header"
        assert data["name"] == "Accept"
        assert data["description"] == "Unsupported media type"
