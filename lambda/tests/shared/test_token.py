"""Tests for TokenResponse model"""

import json

import pytest

from src.shared.token import TokenResponse


class TestTokenResponse:
    """Tests for TokenResponse model"""

    def test_creation_with_all_fields(self):
        """Test creating TokenResponse with all fields"""
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
        """Test that duration is 300 seconds (5 minutes)"""
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
        """Test that hash algorithm is sha256"""
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
        """Test that api_endpoint follows expected format"""
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

    def test_to_json(self):
        """Test serialization to JSON"""
        token = TokenResponse(
            id="json_test_id",
            key="json_test_key",
            api_endpoint="https://sync.example.com/1.5/jsonuser",
            uid=789,
            duration=300,
            hashalg="sha256",
        )

        json_str = token.to_json()
        data = json.loads(json_str)

        assert data["id"] == "json_test_id"
        assert data["key"] == "json_test_key"
        assert data["api_endpoint"] == "https://sync.example.com/1.5/jsonuser"
        assert data["uid"] == 789
        assert data["duration"] == 300
        assert data["hashalg"] == "sha256"

    def test_from_json(self):
        """Test deserialization from JSON"""
        json_str = '{"id": "from_json_id", "key": "from_json_key", "api_endpoint": "https://sync.example.com/1.5/fromjson", "uid": 111, "duration": 300, "hashalg": "sha256"}'
        token = TokenResponse.from_json(json_str)

        assert token.id == "from_json_id"
        assert token.key == "from_json_key"
        assert token.api_endpoint == "https://sync.example.com/1.5/fromjson"
        assert token.uid == 111
        assert token.duration == 300
        assert token.hashalg == "sha256"

    def test_round_trip_serialization(self):
        """Test that serialization and deserialization are inverses"""
        original = TokenResponse(
            id="roundtrip_id",
            key="roundtrip_key_hex",
            api_endpoint="https://sync.example.com/1.5/roundtrip",
            uid=999999,
            duration=300,
            hashalg="sha256",
        )

        json_str = original.to_json()
        restored = TokenResponse.from_json(json_str)

        assert restored.id == original.id
        assert restored.key == original.key
        assert restored.api_endpoint == original.api_endpoint
        assert restored.uid == original.uid
        assert restored.duration == original.duration
        assert restored.hashalg == original.hashalg

    def test_to_dict(self):
        """Test conversion to dictionary"""
        token = TokenResponse(
            id="dict_id",
            key="dict_key",
            api_endpoint="https://sync.example.com/1.5/dictuser",
            uid=555,
            duration=300,
            hashalg="sha256",
        )

        data = token.to_dict()

        assert isinstance(data, dict)
        assert data["id"] == "dict_id"
        assert data["key"] == "dict_key"
        assert data["api_endpoint"] == "https://sync.example.com/1.5/dictuser"
        assert data["uid"] == 555
        assert data["duration"] == 300
        assert data["hashalg"] == "sha256"

    def test_from_dict(self):
        """Test creation from dictionary"""
        data = {
            "id": "fromdict_id",
            "key": "fromdict_key",
            "api_endpoint": "https://sync.example.com/1.5/fromdictuser",
            "uid": 777,
            "duration": 300,
            "hashalg": "sha256",
        }

        token = TokenResponse.from_dict(data)

        assert token.id == "fromdict_id"
        assert token.key == "fromdict_key"
        assert token.api_endpoint == "https://sync.example.com/1.5/fromdictuser"
        assert token.uid == 777
        assert token.duration == 300
        assert token.hashalg == "sha256"

    def test_uid_is_numeric(self):
        """Test that uid is a numeric value"""
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
        """Test that different tokens can have different uids"""
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
