"""Unit tests for OIDCValidator"""

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from jwt import PyJWKClientError

from src.services.oidc_validator import CACHE_TTL_SECONDS, OIDCValidator
from src.shared.exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    ServiceUnavailableError,
)


@pytest.fixture
def provider_url():
    return "https://auth.example.com"


@pytest.fixture
def client_id():
    return "test-client-id"


@pytest.fixture
def validator(provider_url, client_id):
    return OIDCValidator(provider_url, client_id)


@pytest.fixture
def mock_provider_config():
    return {
        "issuer": "https://auth.example.com",
        "jwks_uri": "https://auth.example.com/.well-known/jwks.json",
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "userinfo_endpoint": "https://auth.example.com/userinfo",
    }


class TestOIDCValidatorInit:
    """Test OIDCValidator initialization"""

    def test_init_strips_trailing_slash(self, client_id):
        """Test that trailing slash is stripped from provider URL"""
        validator = OIDCValidator("https://auth.example.com/", client_id)
        assert validator.provider_url == "https://auth.example.com"

    def test_init_stores_client_id(self, provider_url, client_id):
        """Test that client_id is stored correctly"""
        validator = OIDCValidator(provider_url, client_id)
        assert validator.client_id == client_id


class TestDiscoverProviderConfig:
    """Test discover_provider_config method"""

    def test_discover_provider_config_success(self, validator, mock_provider_config):
        """Test successful provider config discovery"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            config = validator.discover_provider_config()

            assert config.issuer == mock_provider_config["issuer"]
            assert config.jwks_uri == mock_provider_config["jwks_uri"]
            mock_get.assert_called_once_with(
                "https://auth.example.com/.well-known/openid-configuration",
                timeout=10,
            )

    def test_discover_provider_config_caching(self, validator, mock_provider_config):
        """Test that provider config is cached"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # First call
            config1 = validator.discover_provider_config()
            # Second call should use cache
            config2 = validator.discover_provider_config()

            assert config1 == config2
            # Should only call once due to caching
            assert mock_get.call_count == 1

    def test_discover_provider_config_cache_expiry(self, validator, mock_provider_config):
        """Test that cache expires after TTL"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # First call
            validator.discover_provider_config()

            # Simulate cache expiry
            validator._provider_config_timestamp = time.time() - CACHE_TTL_SECONDS - 1

            # Second call should fetch again
            validator.discover_provider_config()

            assert mock_get.call_count == 2

    def test_discover_provider_config_timeout(self, validator):
        """Test ServiceUnavailableError on timeout"""
        import requests  # type: ignore[import-untyped]

        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout()

            with pytest.raises(ServiceUnavailableError) as exc_info:
                validator.discover_provider_config()

            assert "timed out" in str(exc_info.value.message)

    def test_discover_provider_config_connection_error(self, validator):
        """Test ServiceUnavailableError on connection error"""
        import requests  # type: ignore[import-untyped]

        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError()

            with pytest.raises(ServiceUnavailableError) as exc_info:
                validator.discover_provider_config()

            assert "unreachable" in str(exc_info.value.message)

    def test_discover_provider_config_http_error(self, validator):
        """Test ServiceUnavailableError on HTTP error"""
        import requests  # type: ignore[import-untyped]

        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=mock_response
            )
            mock_get.return_value = mock_response

            with pytest.raises(ServiceUnavailableError) as exc_info:
                validator.discover_provider_config()

            assert "returned error" in str(exc_info.value.message)

    def test_discover_provider_config_invalid_json(self, validator):
        """Test ServiceUnavailableError on invalid config"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {}  # Missing required fields
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with pytest.raises(ServiceUnavailableError) as exc_info:
                validator.discover_provider_config()

            assert "Invalid OIDC provider configuration" in str(exc_info.value.message)


class TestValidateToken:
    """Test validate_token method"""

    def test_validate_token_success(self, validator, mock_provider_config):
        """Test successful token validation"""
        mock_claims = {
            "sub": "user123",
            "iss": "https://auth.example.com",
            "aud": "test-client-id",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "email": "user@example.com",
        }

        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch.object(validator, "_get_jwk_client") as mock_jwk:
                mock_signing_key = MagicMock()
                mock_signing_key.key = "test-key"
                mock_jwk.return_value.get_signing_key_from_jwt.return_value = mock_signing_key

                with patch("src.services.oidc_validator.jwt.decode") as mock_decode:
                    mock_decode.return_value = mock_claims

                    claims = validator.validate_token("test-token")

                    assert claims.sub == "user123"
                    assert claims.iss == "https://auth.example.com"
                    assert claims.aud == "test-client-id"
                    assert claims.email == "user@example.com"

    def test_validate_token_expired(self, validator, mock_provider_config):
        """Test InvalidCredentialsError on expired token"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch.object(validator, "_get_jwk_client") as mock_jwk:
                mock_signing_key = MagicMock()
                mock_signing_key.key = "test-key"
                mock_jwk.return_value.get_signing_key_from_jwt.return_value = mock_signing_key

                with patch("src.services.oidc_validator.jwt.decode") as mock_decode:
                    mock_decode.side_effect = jwt.ExpiredSignatureError()

                    with pytest.raises(InvalidCredentialsError) as exc_info:
                        validator.validate_token("expired-token")

                    assert "expired" in str(exc_info.value.message)

    def test_validate_token_invalid_audience(self, validator, mock_provider_config):
        """Test InvalidCredentialsError on invalid audience"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch.object(validator, "_get_jwk_client") as mock_jwk:
                mock_signing_key = MagicMock()
                mock_signing_key.key = "test-key"
                mock_jwk.return_value.get_signing_key_from_jwt.return_value = mock_signing_key

                with patch("src.services.oidc_validator.jwt.decode") as mock_decode:
                    mock_decode.side_effect = jwt.InvalidAudienceError()

                    with pytest.raises(InvalidCredentialsError) as exc_info:
                        validator.validate_token("wrong-audience-token")

                    assert "audience" in str(exc_info.value.message)

    def test_validate_token_invalid_issuer(self, validator, mock_provider_config):
        """Test InvalidCredentialsError on invalid issuer"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch.object(validator, "_get_jwk_client") as mock_jwk:
                mock_signing_key = MagicMock()
                mock_signing_key.key = "test-key"
                mock_jwk.return_value.get_signing_key_from_jwt.return_value = mock_signing_key

                with patch("src.services.oidc_validator.jwt.decode") as mock_decode:
                    mock_decode.side_effect = jwt.InvalidIssuerError()

                    with pytest.raises(InvalidCredentialsError) as exc_info:
                        validator.validate_token("wrong-issuer-token")

                    assert "issuer" in str(exc_info.value.message)

    def test_validate_token_missing_sub_claim(self, validator, mock_provider_config):
        """Test InvalidCredentialsError when sub claim is missing"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch.object(validator, "_get_jwk_client") as mock_jwk:
                mock_signing_key = MagicMock()
                mock_signing_key.key = "test-key"
                mock_jwk.return_value.get_signing_key_from_jwt.return_value = mock_signing_key

                with patch("src.services.oidc_validator.jwt.decode") as mock_decode:
                    mock_decode.side_effect = jwt.MissingRequiredClaimError("sub")

                    with pytest.raises(InvalidCredentialsError) as exc_info:
                        validator.validate_token("no-sub-token")

                    assert "missing required claim" in str(exc_info.value.message).lower()

    def test_validate_token_invalid_signature(self, validator, mock_provider_config):
        """Test InvalidTokenError on invalid signature"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch.object(validator, "_get_jwk_client") as mock_jwk:
                mock_signing_key = MagicMock()
                mock_signing_key.key = "test-key"
                mock_jwk.return_value.get_signing_key_from_jwt.return_value = mock_signing_key

                with patch("src.services.oidc_validator.jwt.decode") as mock_decode:
                    mock_decode.side_effect = jwt.InvalidSignatureError()

                    with pytest.raises(InvalidTokenError) as exc_info:
                        validator.validate_token("bad-signature-token")

                    assert "Invalid token" in str(exc_info.value.message)

    def test_validate_token_jwk_client_error(self, validator, mock_provider_config):
        """Test InvalidTokenError when JWK client fails"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch.object(validator, "_get_jwk_client") as mock_jwk:
                mock_jwk.return_value.get_signing_key_from_jwt.side_effect = PyJWKClientError(
                    "Key not found"
                )

                with pytest.raises(InvalidTokenError) as exc_info:
                    validator.validate_token("unknown-key-token")

                assert "signing key" in str(exc_info.value.message)

    def test_validate_token_audience_as_list(self, validator, mock_provider_config):
        """Test handling of audience claim as list"""
        mock_claims = {
            "sub": "user123",
            "iss": "https://auth.example.com",
            "aud": ["test-client-id", "other-client"],
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }

        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch.object(validator, "_get_jwk_client") as mock_jwk:
                mock_signing_key = MagicMock()
                mock_signing_key.key = "test-key"
                mock_jwk.return_value.get_signing_key_from_jwt.return_value = mock_signing_key

                with patch("src.services.oidc_validator.jwt.decode") as mock_decode:
                    mock_decode.return_value = mock_claims

                    claims = validator.validate_token("test-token")

                    # Should take first audience from list
                    assert claims.aud == "test-client-id"

    def test_validate_token_empty_sub_claim(self, validator, mock_provider_config):
        """Test InvalidCredentialsError when sub claim is empty string"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch.object(validator, "_get_jwk_client") as mock_jwk:
                mock_signing_key = MagicMock()
                mock_signing_key.key = "test-key"
                mock_jwk.return_value.get_signing_key_from_jwt.return_value = mock_signing_key

                with patch("src.services.oidc_validator.jwt.decode") as mock_decode:
                    mock_decode.return_value = {
                        "sub": "",  # Empty string
                        "iss": "https://auth.example.com",
                        "aud": "test-client-id",
                        "exp": int(time.time()) + 3600,
                        "iat": int(time.time()),
                    }

                    with pytest.raises(InvalidCredentialsError) as exc_info:
                        validator.validate_token("empty-sub-token")

                    assert "sub claim" in str(exc_info.value.message)

    def test_validate_token_empty_audience_list(self, validator, mock_provider_config):
        """Test handling of empty audience list"""
        mock_claims = {
            "sub": "user123",
            "iss": "https://auth.example.com",
            "aud": [],  # Empty list
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }

        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch.object(validator, "_get_jwk_client") as mock_jwk:
                mock_signing_key = MagicMock()
                mock_signing_key.key = "test-key"
                mock_jwk.return_value.get_signing_key_from_jwt.return_value = mock_signing_key

                with patch("src.services.oidc_validator.jwt.decode") as mock_decode:
                    mock_decode.return_value = mock_claims

                    claims = validator.validate_token("test-token")

                    # Should return empty string for empty audience list
                    assert claims.aud == ""

    def test_validate_token_unexpected_exception(self, validator, mock_provider_config):
        """Test InvalidTokenError on unexpected exception"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch.object(validator, "_get_jwk_client") as mock_jwk:
                mock_signing_key = MagicMock()
                mock_signing_key.key = "test-key"
                mock_jwk.return_value.get_signing_key_from_jwt.return_value = mock_signing_key

                with patch("src.services.oidc_validator.jwt.decode") as mock_decode:
                    # Simulate an unexpected error by raising a non-JWT exception
                    mock_decode.side_effect = TypeError("Unexpected type error")

                    with pytest.raises(InvalidTokenError) as exc_info:
                        validator.validate_token("test-token")

                    assert "Token validation failed" in str(exc_info.value.message)

    def test_validate_token_service_unavailable_reraise(self, validator):
        """Test ServiceUnavailableError is re-raised during token validation"""
        with patch.object(validator, "discover_provider_config") as mock_discover:
            mock_discover.side_effect = ServiceUnavailableError("Provider unreachable")

            with pytest.raises(ServiceUnavailableError) as exc_info:
                validator.validate_token("test-token")

            assert "Provider unreachable" in str(exc_info.value.message)


class TestGetJwkClient:
    """Test _get_jwk_client method"""

    def test_get_jwk_client_creates_client(self, validator, mock_provider_config):
        """Test that _get_jwk_client creates PyJWKClient on first call"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch("src.services.oidc_validator.PyJWKClient") as mock_jwk_class:
                mock_jwk_instance = MagicMock()
                mock_jwk_class.return_value = mock_jwk_instance

                client = validator._get_jwk_client()

                assert client is mock_jwk_instance
                mock_jwk_class.assert_called_once_with(
                    mock_provider_config["jwks_uri"],
                    cache_keys=True,
                    lifespan=CACHE_TTL_SECONDS,
                )

    def test_get_jwk_client_caches_client(self, validator, mock_provider_config):
        """Test that _get_jwk_client returns cached client on subsequent calls"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            with patch("src.services.oidc_validator.PyJWKClient") as mock_jwk_class:
                mock_jwk_instance = MagicMock()
                mock_jwk_class.return_value = mock_jwk_instance

                # First call
                client1 = validator._get_jwk_client()
                # Second call should use cache
                client2 = validator._get_jwk_client()

                assert client1 is client2
                # Should only create once
                assert mock_jwk_class.call_count == 1


class TestClearCache:
    """Test clear_cache method"""

    def test_clear_cache(self, validator, mock_provider_config):
        """Test that clear_cache resets all cached data"""
        with patch("src.services.oidc_validator.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_provider_config
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # Populate cache
            validator.discover_provider_config()
            assert validator._provider_config is not None

            # Clear cache
            validator.clear_cache()

            assert validator._provider_config is None
            assert validator._provider_config_timestamp == 0
            assert validator._jwk_client is None
