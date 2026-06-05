"""Tests for TokenResponse model"""

from dataclasses import asdict

from src.shared.token import TokenResponse


class TestTokenResponse:
    """Tests for TokenResponse model"""

    def test_creation_with_all_fields(self):
        token = TokenResponse(
            id="hawk_id_base64",
            key="hawk_key_hex_64_chars",
            api_endpoint="https://sync.example.com/1.5/user123",
            uid=12345,
            duration=300,
            hashalg="sha256",
        )

        assert token.id == "hawk_id_base64"
        assert token.key == "hawk_key_hex_64_chars"
        assert token.api_endpoint == "https://sync.example.com/1.5/user123"
        assert token.uid == 12345
        assert token.duration == 300
        assert token.hashalg == "sha256"

    def test_duration_is_300_seconds(self):
        token = TokenResponse(
            id="test_id",
            key="test_key",
            api_endpoint="https://sync.example.com/1.5/user",
            uid=999,
            duration=300,
            hashalg="sha256",
        )
        assert token.duration == 300

    def test_hashalg_is_sha256(self):
        token = TokenResponse(
            id="test_id",
            key="test_key",
            api_endpoint="https://sync.example.com/1.5/user",
            uid=999,
            duration=300,
            hashalg="sha256",
        )
        assert token.hashalg == "sha256"

    def test_api_endpoint_format(self):
        token = TokenResponse(
            id="test_id",
            key="test_key",
            api_endpoint="https://sync.example.com/1.5/user456",
            uid=456,
            duration=300,
            hashalg="sha256",
        )
        assert token.api_endpoint.startswith("https://")
        assert "/1.5/" in token.api_endpoint
        assert token.api_endpoint.endswith("user456")

    def test_asdict(self):
        token = TokenResponse(
            id="dict_id",
            key="dict_key",
            api_endpoint="https://sync.example.com/1.5/dictuser",
            uid=555,
            duration=300,
            hashalg="sha256",
        )

        data = asdict(token)

        assert isinstance(data, dict)
        assert data["id"] == "dict_id"
        assert data["key"] == "dict_key"
        assert data["api_endpoint"] == "https://sync.example.com/1.5/dictuser"
        assert data["uid"] == 555
        assert data["duration"] == 300
        assert data["hashalg"] == "sha256"

    def test_uid_is_numeric(self):
        token = TokenResponse(
            id="test_id",
            key="test_key",
            api_endpoint="https://sync.example.com/1.5/user",
            uid=12345,
            duration=300,
            hashalg="sha256",
        )
        assert isinstance(token.uid, int)
        assert token.uid > 0

    def test_different_uids_for_different_users(self):
        token1 = TokenResponse(
            id="id1",
            key="key1",
            api_endpoint="https://sync.example.com/1.5/user1",
            uid=100,
            duration=300,
            hashalg="sha256",
        )
        token2 = TokenResponse(
            id="id2",
            key="key2",
            api_endpoint="https://sync.example.com/1.5/user2",
            uid=200,
            duration=300,
            hashalg="sha256",
        )
        assert token1.uid != token2.uid
