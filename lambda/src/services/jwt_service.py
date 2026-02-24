"""JWT Service for signing OAuth tokens with KMS and providing JWKS public keys."""

import base64
import hashlib
import json
import time
from typing import Any, Optional

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key


class JWTService:
    """Signs OAuth JWTs using KMS and exposes the public key as JWK."""

    def __init__(self, kms_client: Any, signing_key_id: str, issuer: str):
        self._kms = kms_client
        self._signing_key_id = signing_key_id
        self._issuer = issuer
        self._cached_jwk: Optional[dict] = None
        self._cached_kid: Optional[str] = None

    @property
    def issuer(self) -> str:
        return self._issuer

    def _b64url(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    def _get_kid(self) -> str:
        if self._cached_kid is None:
            self.get_public_key_jwk()
        assert self._cached_kid is not None
        return self._cached_kid

    def sign_jwt(
        self,
        sub: str,
        scope: str,
        ttl: int,
        client_id: Optional[str] = None,
    ) -> str:
        """Sign a JWT using KMS.

        Args:
            sub: Subject claim (user identifier).
            scope: OAuth scope string.
            ttl: Token time-to-live in seconds.
            client_id: Optional OAuth client ID.

        Returns:
            Compact JWT string (header.payload.signature).
        """
        now = int(time.time())
        kid = self._get_kid()

        header = {"alg": "RS256", "typ": "JWT", "kid": kid}
        payload: dict[str, Any] = {
            "sub": sub,
            "iss": self._issuer,
            "iat": now,
            "exp": now + ttl,
            "scope": scope,
        }
        if client_id is not None:
            payload["client_id"] = client_id

        header_b64 = self._b64url(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = self._b64url(json.dumps(payload, separators=(",", ":")).encode())

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

        response = self._kms.sign(
            KeyId=self._signing_key_id,
            Message=signing_input,
            MessageType="RAW",
            SigningAlgorithm="RSASSA_PKCS1_V1_5_SHA_256",
        )

        signature_b64 = self._b64url(response["Signature"])
        return f"{header_b64}.{payload_b64}.{signature_b64}"

    def get_public_key_jwk(self) -> dict:
        """Get the public key in JWK format.

        Calls KMS GetPublicKey on first invocation and caches the result.

        Returns:
            JWK dict with kty, n, e, alg, use, kid fields.
        """
        if self._cached_jwk is not None:
            return self._cached_jwk

        response = self._kms.get_public_key(KeyId=self._signing_key_id)
        public_key_der = response["PublicKey"]

        # Parse the DER-encoded SubjectPublicKeyInfo
        public_key = load_der_public_key(public_key_der)
        assert isinstance(public_key, RSAPublicKey)
        pub_numbers = public_key.public_numbers()

        # Convert RSA public key numbers to JWK format
        n_bytes = pub_numbers.n.to_bytes((pub_numbers.n.bit_length() + 7) // 8, byteorder="big")
        e_bytes = pub_numbers.e.to_bytes((pub_numbers.e.bit_length() + 7) // 8, byteorder="big")

        # Generate kid from the key fingerprint
        kid = hashlib.sha256(public_key_der).hexdigest()[:16]

        self._cached_kid = kid
        self._cached_jwk = {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": kid,
            "n": self._b64url(n_bytes),
            "e": self._b64url(e_bytes),
        }
        return self._cached_jwk
