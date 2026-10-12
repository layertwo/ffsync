"""JWT Service for signing OAuth tokens with KMS and providing JWKS public keys."""

import hashlib
import json
import time
from functools import cached_property
from typing import Any, Optional

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key

from src.shared.utils import b64url_encode


class JWTService:
    """Signs OAuth JWTs using KMS and exposes the public key as JWK."""

    def __init__(self, kms_client: Any, signing_key_id: str, issuer: str):
        self._kms = kms_client
        self._signing_key_id = signing_key_id
        self._issuer = issuer

    @property
    def issuer(self) -> str:
        return self._issuer

    def _get_kid(self) -> str:
        return str(self._jwk["kid"])

    def sign_jwt(
        self,
        sub: str,
        scope: str,
        ttl: int,
        client_id: Optional[str] = None,
        fxa_uid: Optional[str] = None,
    ) -> str:
        """Sign a JWT using KMS.

        Args:
            sub: Subject claim (OIDC subject identifier).
            scope: OAuth scope string.
            ttl: Token time-to-live in seconds.
            client_id: Optional OAuth client ID.
            fxa_uid: Optional internal FxA account uid for profile lookups.

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
        if fxa_uid is not None:
            payload["fxa_uid"] = fxa_uid

        header_b64 = b64url_encode(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = b64url_encode(json.dumps(payload, separators=(",", ":")).encode())

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

        response = self._kms.sign(
            KeyId=self._signing_key_id,
            Message=signing_input,
            MessageType="RAW",
            SigningAlgorithm="RSASSA_PKCS1_V1_5_SHA_256",
        )

        signature_b64 = b64url_encode(response["Signature"])
        return f"{header_b64}.{payload_b64}.{signature_b64}"

    def get_public_key_jwk(self) -> dict:
        """Get the public key in JWK format.

        Returns:
            JWK dict with kty, n, e, alg, use, kid fields.
        """
        return self._jwk

    @cached_property
    def _jwk(self) -> dict:
        """Fetch the KMS public key as a JWK, once per instance."""
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

        return {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": kid,
            "n": b64url_encode(n_bytes),
            "e": b64url_encode(e_bytes),
        }
