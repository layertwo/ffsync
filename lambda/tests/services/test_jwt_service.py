"""Unit tests for JWT Service (KMS signing)"""

import base64
import json
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

from src.services.jwt_service import JWTService


def _generate_test_rsa_key():
    """Generate a test RSA key pair for round-trip testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    public_key_der = public_key.public_bytes(
        encoding=Encoding.DER,
        format=PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_key_der


@pytest.fixture
def rsa_keys():
    return _generate_test_rsa_key()


@pytest.fixture
def mock_kms(rsa_keys):
    _, public_key_der = rsa_keys
    client = MagicMock()
    client.get_public_key.return_value = {
        "PublicKey": public_key_der,
        "KeyId": "key-123",
        "KeySpec": "RSA_2048",
        "SigningAlgorithms": ["RSASSA_PKCS1_V1_5_SHA_256"],
    }
    client.sign.return_value = {
        "Signature": b"\x00" * 256,
        "SigningAlgorithm": "RSASSA_PKCS1_V1_5_SHA_256",
    }
    return client


@pytest.fixture
def service(mock_kms):
    return JWTService(
        kms_client=mock_kms,
        signing_key_id="key-123",
        issuer="https://auth.prod.ffsync.layertwo.dev",
    )


class TestIssuerProperty:
    def test_returns_issuer(self, service):
        assert service.issuer == "https://auth.prod.ffsync.layertwo.dev"


class TestSignJWT:
    def test_returns_three_part_jwt(self, service):
        token = service.sign_jwt(
            sub="user1",
            scope="https://identity.mozilla.com/apps/oldsync",
            ttl=300,
        )
        parts = token.split(".")
        assert len(parts) == 3

    def test_header_specifies_rs256(self, service):
        token = service.sign_jwt(sub="user1", scope="openid", ttl=300)
        # Add padding for base64 decode
        header_b64 = token.split(".")[0]
        header_b64 += "=" * (4 - len(header_b64) % 4)
        header = json.loads(base64.urlsafe_b64decode(header_b64))
        assert header["alg"] == "RS256"
        assert header["typ"] == "JWT"
        assert "kid" in header

    def test_payload_contains_claims(self, service):
        token = service.sign_jwt(sub="user1", scope="openid", ttl=300)
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert payload["sub"] == "user1"
        assert payload["iss"] == "https://auth.prod.ffsync.layertwo.dev"
        assert payload["scope"] == "openid"
        assert "exp" in payload
        assert "iat" in payload
        assert payload["exp"] - payload["iat"] == 300

    def test_payload_contains_client_id(self, service):
        token = service.sign_jwt(sub="user1", scope="openid", ttl=300, client_id="test-client")
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert payload["client_id"] == "test-client"

    def test_payload_omits_client_id_when_none(self, service):
        token = service.sign_jwt(sub="user1", scope="openid", ttl=300)
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert "client_id" not in payload

    def test_payload_contains_fxa_uid(self, service):
        token = service.sign_jwt(sub="oidc-sub", scope="openid", ttl=300, fxa_uid="uid1")
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert payload["fxa_uid"] == "uid1"

    def test_payload_omits_fxa_uid_when_none(self, service):
        token = service.sign_jwt(sub="user1", scope="openid", ttl=300)
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert "fxa_uid" not in payload

    def test_calls_kms_sign(self, service, mock_kms):
        service.sign_jwt(sub="user1", scope="openid", ttl=300)
        mock_kms.sign.assert_called_once()
        call_kwargs = mock_kms.sign.call_args.kwargs
        assert call_kwargs["KeyId"] == "key-123"
        assert call_kwargs["SigningAlgorithm"] == "RSASSA_PKCS1_V1_5_SHA_256"
        assert call_kwargs["MessageType"] == "RAW"

    def test_different_subs_produce_different_tokens(self, service):
        token1 = service.sign_jwt(sub="user1", scope="openid", ttl=300)
        token2 = service.sign_jwt(sub="user2", scope="openid", ttl=300)
        # Headers may be the same but payloads should differ
        assert token1.split(".")[1] != token2.split(".")[1]


class TestGetPublicKeyJWK:
    def test_returns_jwk_dict(self, service):
        jwk = service.get_public_key_jwk()
        assert isinstance(jwk, dict)
        assert jwk["kty"] == "RSA"
        assert jwk["use"] == "sig"
        assert jwk["alg"] == "RS256"
        assert "n" in jwk
        assert "e" in jwk
        assert "kid" in jwk

    def test_caches_public_key(self, service, mock_kms):
        service.get_public_key_jwk()
        service.get_public_key_jwk()
        # Should only call KMS once due to caching
        mock_kms.get_public_key.assert_called_once()

    def test_kid_matches_header(self, service):
        jwk = service.get_public_key_jwk()
        token = service.sign_jwt(sub="user1", scope="openid", ttl=300)
        header_b64 = token.split(".")[0]
        header_b64 += "=" * (4 - len(header_b64) % 4)
        header = json.loads(base64.urlsafe_b64decode(header_b64))
        assert header["kid"] == jwk["kid"]
