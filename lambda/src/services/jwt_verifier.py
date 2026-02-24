"""JWT Verifier for validating self-issued OAuth access tokens."""

import base64
import json
import time

from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.primitives.hashes import SHA256

from src.services.jwt_service import JWTService
from src.shared.exceptions import InvalidTokenError
from src.shared.oidc import OIDCTokenClaims


class JWTVerifier:
    """Validates self-issued JWTs using the public key from JWTService."""

    def __init__(self, jwt_service: JWTService, clock_skew_tolerance: int = 60):
        self._jwt_service = jwt_service
        self._clock_skew_tolerance = clock_skew_tolerance

    def validate_token(self, token: str) -> OIDCTokenClaims:
        """Validate a self-issued JWT access token.

        Args:
            token: Compact JWT string (header.payload.signature).

        Returns:
            OIDCTokenClaims with sub, iss, exp, iat, aud fields.

        Raises:
            InvalidTokenError: If the token is invalid, expired, or unverifiable.
        """
        parts = token.split(".")
        if len(parts) != 3:
            raise InvalidTokenError("Invalid JWT format")

        header_b64, payload_b64, signature_b64 = parts

        # Decode header
        try:
            header = json.loads(self._b64url_decode(header_b64))
        except Exception as e:
            raise InvalidTokenError(f"Invalid JWT header: {e}") from e

        if header.get("alg") != "RS256":
            raise InvalidTokenError(f"Unsupported algorithm: {header.get('alg')}")

        # Decode payload
        try:
            payload = json.loads(self._b64url_decode(payload_b64))
        except Exception as e:
            raise InvalidTokenError(f"Invalid JWT payload: {e}") from e

        # Verify required claims
        for claim in ("sub", "iss", "exp", "iat"):
            if claim not in payload:
                raise InvalidTokenError(f"Missing required claim: {claim}")

        # Validate issuer
        expected_issuer = self._jwt_service.issuer
        if payload.get("iss") != expected_issuer:
            raise InvalidTokenError(f"Invalid issuer: {payload.get('iss')}")

        # Check expiry
        now = int(time.time())
        if payload["exp"] < now - self._clock_skew_tolerance:
            raise InvalidTokenError("Token expired")

        # Verify signature using cached public key
        self._verify_signature(header_b64, payload_b64, signature_b64)

        return OIDCTokenClaims(
            sub=payload["sub"],
            iss=payload["iss"],
            aud=payload.get("client_id", ""),
            exp=payload["exp"],
            iat=payload["iat"],
        )

    def _verify_signature(self, header_b64: str, payload_b64: str, signature_b64: str) -> None:
        """Verify the JWT signature against the KMS public key."""
        jwk = self._jwt_service.get_public_key_jwk()

        # Reconstruct RSA public key from JWK
        n_bytes = self._b64url_decode(jwk["n"])
        e_bytes = self._b64url_decode(jwk["e"])

        n = int.from_bytes(n_bytes, byteorder="big")
        e = int.from_bytes(e_bytes, byteorder="big")

        public_key = RSAPublicNumbers(e, n).public_key()

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        signature = self._b64url_decode(signature_b64)

        try:
            public_key.verify(signature, signing_input, PKCS1v15(), SHA256())
        except Exception as e:
            raise InvalidTokenError(f"Invalid signature: {e}") from e

    @staticmethod
    def _b64url_decode(data: str) -> bytes:
        """Decode base64url-encoded data with padding."""
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data)
