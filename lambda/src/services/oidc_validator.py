"""OIDC Validator for token validation against configured OIDC providers"""

import time
from typing import Optional

import jwt
import requests  # type: ignore[import-untyped]
from jwt import PyJWKClient, PyJWKClientError

from src.shared.exceptions import (
    InvalidCredentialsError,
    InvalidTimestampError,
    InvalidTokenError,
    ServiceUnavailableError,
)
from src.shared.oidc import OIDCProviderConfig, OIDCTokenClaims

# Cache TTL in seconds (1 hour)
CACHE_TTL_SECONDS = 3600


class OIDCValidator:
    """
    Validates OIDC tokens against a configured provider.

    Handles:
    - Discovery of provider configuration from .well-known/openid-configuration
    - JWKS fetching and caching
    - Token signature verification
    - Claims validation (issuer, audience, expiry)
    - User identifier extraction from sub claim
    """

    def __init__(self, provider_url: str, client_id: str, clock_skew_tolerance: int = 300):
        """
        Initialize OIDC validator with provider configuration.

        Args:
            provider_url: Base URL of OIDC provider (e.g., https://auth.example.com)
            client_id: Expected audience claim value (OAuth client ID)
            clock_skew_tolerance: Maximum allowed clock skew in seconds (default 300 / 5 minutes)
        """
        self.provider_url = provider_url.rstrip("/")
        self.client_id = client_id
        self.clock_skew_tolerance = clock_skew_tolerance
        self._provider_config: Optional[OIDCProviderConfig] = None
        self._provider_config_timestamp: float = 0
        self._jwk_client: Optional[PyJWKClient] = None

    def _is_cache_valid(self) -> bool:
        """Check if the cached provider configuration is still valid."""
        if self._provider_config is None:
            return False
        return (time.time() - self._provider_config_timestamp) < CACHE_TTL_SECONDS

    def discover_provider_config(self) -> OIDCProviderConfig:
        """
        Fetch OIDC provider configuration from .well-known endpoint.

        Caches the configuration for 1 hour to reduce external API calls.

        Returns:
            OIDCProviderConfig with provider endpoints

        Raises:
            ServiceUnavailableError: If provider is unreachable
        """
        # Return cached config if still valid
        if self._is_cache_valid() and self._provider_config is not None:
            return self._provider_config

        well_known_url = f"{self.provider_url}/.well-known/openid-configuration"

        try:
            response = requests.get(well_known_url, timeout=10)
            response.raise_for_status()
            config_data = response.json()

            self._provider_config = OIDCProviderConfig(
                issuer=config_data["issuer"],
                jwks_uri=config_data["jwks_uri"],
                authorization_endpoint=config_data.get("authorization_endpoint", ""),
                token_endpoint=config_data.get("token_endpoint", ""),
                userinfo_endpoint=config_data.get("userinfo_endpoint", ""),
            )
            self._provider_config_timestamp = time.time()

            # Reset JWK client to use new JWKS URI
            self._jwk_client = None

            return self._provider_config

        except requests.exceptions.Timeout:
            raise ServiceUnavailableError("OIDC provider request timed out")
        except requests.exceptions.ConnectionError:
            raise ServiceUnavailableError("OIDC provider is unreachable")
        except requests.exceptions.HTTPError as e:
            raise ServiceUnavailableError(f"OIDC provider returned error: {e.response.status_code}")
        except (KeyError, ValueError) as e:
            raise ServiceUnavailableError(f"Invalid OIDC provider configuration: {e}")

    def _get_jwk_client(self) -> PyJWKClient:
        """
        Get or create PyJWKClient for JWKS fetching.

        The PyJWKClient handles caching of JWKS internally.

        Returns:
            PyJWKClient instance

        Raises:
            ServiceUnavailableError: If provider config cannot be fetched
        """
        if self._jwk_client is None:
            config = self.discover_provider_config()
            self._jwk_client = PyJWKClient(
                config.jwks_uri,
                cache_keys=True,
                lifespan=CACHE_TTL_SECONDS,
            )
        return self._jwk_client

    def validate_token(self, token: str) -> OIDCTokenClaims:
        """
        Validate OIDC token and extract claims.

        Performs the following validations:
        1. Fetches signing key from JWKS endpoint
        2. Verifies token signature
        3. Validates issuer matches configured provider
        4. Validates audience matches configured client_id
        5. Verifies token has not expired
        6. Validates token timestamp (iat) against server time with tolerance
        7. Extracts user identifier from sub claim

        Args:
            token: Raw OIDC token string (JWT)

        Returns:
            OIDCTokenClaims with validated claims

        Raises:
            InvalidTokenError: If token signature is invalid
            InvalidCredentialsError: If token is expired or claims are invalid
            InvalidTimestampError: If token timestamp differs too much from server time
            ServiceUnavailableError: If OIDC provider is unreachable
        """
        try:
            # Get provider config for issuer validation
            config = self.discover_provider_config()

            # Get signing key from JWKS
            jwk_client = self._get_jwk_client()
            try:
                signing_key = jwk_client.get_signing_key_from_jwt(token)
            except PyJWKClientError as e:
                raise InvalidTokenError(f"Failed to get signing key: {e}")

            # Decode and validate token
            try:
                claims = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
                    audience=self.client_id,
                    issuer=config.issuer,
                    options={
                        "verify_signature": True,
                        "verify_exp": True,
                        "verify_iat": True,
                        "verify_aud": True,
                        "verify_iss": True,
                        "require": ["sub", "exp", "iat", "iss", "aud"],
                    },
                )
            except jwt.ExpiredSignatureError:
                raise InvalidCredentialsError("Token has expired")
            except jwt.InvalidAudienceError:
                raise InvalidCredentialsError("Token audience does not match expected client ID")
            except jwt.InvalidIssuerError:
                raise InvalidCredentialsError("Token issuer does not match configured provider")
            except jwt.MissingRequiredClaimError as e:
                raise InvalidCredentialsError(f"Token missing required claim: {e}")
            except jwt.InvalidTokenError as e:
                raise InvalidTokenError(f"Invalid token: {e}")

            # Validate timestamp (iat claim) against server time
            server_time = int(time.time())

            iat = claims.get("iat")
            if iat is not None:
                time_diff = abs(server_time - iat)
                if time_diff > self.clock_skew_tolerance:
                    raise InvalidTimestampError(
                        f"Token timestamp differs from server time by {time_diff} seconds "
                        f"(tolerance: {self.clock_skew_tolerance} seconds)"
                    )

            # Extract and validate sub claim
            sub = claims.get("sub")
            if not sub:
                raise InvalidCredentialsError("Token missing user identifier (sub claim)")

            # Handle audience that can be string or list
            aud = claims.get("aud", "")
            if isinstance(aud, list):
                aud = aud[0] if aud else ""

            return OIDCTokenClaims(
                sub=sub,
                iss=claims["iss"],
                aud=aud,
                exp=claims["exp"],
                iat=claims.get("iat", 0),  # Default to 0 if iat is missing
                email=claims.get("email"),
            )

        except (InvalidTokenError, InvalidCredentialsError, InvalidTimestampError):
            # Re-raise our custom exceptions
            raise
        except ServiceUnavailableError:
            # Re-raise service unavailable
            raise
        except Exception as e:
            # Catch any unexpected errors
            raise InvalidTokenError(f"Token validation failed: {e}")

    def clear_cache(self) -> None:
        """
        Clear cached provider configuration and JWKS.

        Useful for testing or when provider configuration changes.
        """
        self._provider_config = None
        self._provider_config_timestamp = 0
        self._jwk_client = None
