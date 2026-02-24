"""Unit tests for JWTVerifier"""

import base64
import json
import time
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.hashes import SHA256

from src.services.jwt_verifier import JWTVerifier
from src.shared.exceptions import InvalidTokenError


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _generate_test_keypair():
    """Generate an RSA keypair for testing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    pub_numbers = public_key.public_numbers()

    n_bytes = pub_numbers.n.to_bytes((pub_numbers.n.bit_length() + 7) // 8, byteorder="big")
    e_bytes = pub_numbers.e.to_bytes((pub_numbers.e.bit_length() + 7) // 8, byteorder="big")

    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": "test-kid",
        "n": _b64url(n_bytes),
        "e": _b64url(e_bytes),
    }
    return private_key, jwk


def _sign_jwt(private_key, payload: dict, header: dict | None = None) -> str:
    """Sign a JWT with the given private key."""
    if header is None:
        header = {"alg": "RS256", "typ": "JWT", "kid": "test-kid"}

    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = private_key.sign(signing_input, PKCS1v15(), SHA256())
    signature_b64 = _b64url(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


@pytest.fixture
def keypair():
    return _generate_test_keypair()


@pytest.fixture
def mock_jwt_service(keypair):
    _, jwk = keypair
    svc = MagicMock()
    svc.get_public_key_jwk.return_value = jwk
    svc.issuer = "https://auth.example.com"
    return svc


@pytest.fixture
def verifier(mock_jwt_service):
    return JWTVerifier(jwt_service=mock_jwt_service)


class TestJWTVerifier:
    def test_valid_token(self, verifier, keypair):
        private_key, _ = keypair
        now = int(time.time())
        payload = {
            "sub": "user123",
            "iss": "https://auth.example.com",
            "iat": now,
            "exp": now + 900,
            "scope": "openid",
        }
        token = _sign_jwt(private_key, payload)
        claims = verifier.validate_token(token)
        assert claims.sub == "user123"
        assert claims.iss == "https://auth.example.com"
        assert claims.exp == now + 900

    def test_expired_token_raises(self, verifier, keypair):
        private_key, _ = keypair
        now = int(time.time())
        payload = {
            "sub": "user123",
            "iss": "https://auth.example.com",
            "iat": now - 2000,
            "exp": now - 1000,
        }
        token = _sign_jwt(private_key, payload)
        with pytest.raises(InvalidTokenError, match="expired"):
            verifier.validate_token(token)

    def test_invalid_signature_raises(self, verifier):
        # Sign with a different key
        other_private_key, _ = _generate_test_keypair()
        now = int(time.time())
        payload = {
            "sub": "user123",
            "iss": "https://auth.example.com",
            "iat": now,
            "exp": now + 900,
        }
        token = _sign_jwt(other_private_key, payload)
        with pytest.raises(InvalidTokenError, match="signature"):
            verifier.validate_token(token)

    def test_missing_sub_raises(self, verifier, keypair):
        private_key, _ = keypair
        now = int(time.time())
        payload = {"iss": "https://auth.example.com", "iat": now, "exp": now + 900}
        token = _sign_jwt(private_key, payload)
        with pytest.raises(InvalidTokenError, match="sub"):
            verifier.validate_token(token)

    def test_missing_exp_raises(self, verifier, keypair):
        private_key, _ = keypair
        now = int(time.time())
        payload = {"sub": "user123", "iss": "https://auth.example.com", "iat": now}
        token = _sign_jwt(private_key, payload)
        with pytest.raises(InvalidTokenError, match="exp"):
            verifier.validate_token(token)

    def test_invalid_jwt_format_raises(self, verifier):
        with pytest.raises(InvalidTokenError, match="format"):
            verifier.validate_token("not-a-jwt")

    def test_unsupported_algorithm_raises(self, verifier, keypair):
        private_key, _ = keypair
        now = int(time.time())
        payload = {
            "sub": "user123",
            "iss": "https://auth.example.com",
            "iat": now,
            "exp": now + 900,
        }
        token = _sign_jwt(private_key, payload, header={"alg": "HS256", "typ": "JWT"})
        with pytest.raises(InvalidTokenError, match="algorithm"):
            verifier.validate_token(token)

    def test_invalid_header_base64_raises(self, verifier):
        # Create a token with invalid base64 header
        token = "!!!invalid!!!.eyJzdWIiOiJ0ZXN0In0.signature"
        with pytest.raises(InvalidTokenError, match="header"):
            verifier.validate_token(token)

    def test_invalid_payload_base64_raises(self, verifier, keypair):
        # Create a token with valid header but invalid payload
        header_b64 = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        token = f"{header_b64}.!!!invalid!!!.signature"
        with pytest.raises(InvalidTokenError, match="payload"):
            verifier.validate_token(token)

    def test_invalid_issuer_raises(self, verifier, keypair):
        private_key, _ = keypair
        now = int(time.time())
        payload = {
            "sub": "user123",
            "iss": "https://evil.example.com",
            "iat": now,
            "exp": now + 900,
        }
        token = _sign_jwt(private_key, payload)
        with pytest.raises(InvalidTokenError, match="issuer"):
            verifier.validate_token(token)

    def test_client_id_mapped_to_aud(self, verifier, keypair):
        private_key, _ = keypair
        now = int(time.time())
        payload = {
            "sub": "user123",
            "iss": "https://auth.example.com",
            "iat": now,
            "exp": now + 900,
            "client_id": "my-client",
        }
        token = _sign_jwt(private_key, payload)
        claims = verifier.validate_token(token)
        assert claims.aud == "my-client"
