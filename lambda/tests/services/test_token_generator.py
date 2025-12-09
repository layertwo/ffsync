"""Unit tests for TokenGenerator"""

import base64
import re
from unittest.mock import patch

import pytest

from src.services.token_generator import TokenGenerator
from src.shared.token import TokenResponse


class TestTokenGenerator:
    """Test TokenGenerator functionality"""

    @pytest.fixture
    def base_url(self):
        return "https://sync.example.com"

    @pytest.fixture
    def token_generator(self, base_url):
        return TokenGenerator(base_url=base_url)

    @pytest.fixture
    def mock_time(self):
        return 1702345678

    @pytest.fixture
    def mock_hawk_key(self):
        # 32 bytes = 64 hex characters
        return "a" * 64

    def test_init_strips_trailing_slash(self):
        """Test that base_url trailing slash is stripped"""
        generator = TokenGenerator(base_url="https://sync.example.com/")
        assert generator.base_url == "https://sync.example.com"

    def test_generate_hawk_id_format(self, token_generator):
        """Test HAWK ID is URL-safe base64 encoded"""
        user_id = "user123"
        generation = 5
        expiry = 1702345978

        hawk_id = token_generator.generate_hawk_id(user_id, generation, expiry)

        # Should be URL-safe base64 (no +, /, or = padding)
        assert "+" not in hawk_id
        assert "/" not in hawk_id
        # Padding is stripped
        assert not hawk_id.endswith("=")

        # Should decode to user_id:generation:expiry
        # Add padding back for decoding
        padded = hawk_id + "=" * (4 - len(hawk_id) % 4) if len(hawk_id) % 4 else hawk_id
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
        assert decoded == f"{user_id}:{generation}:{expiry}"

    def test_generate_hawk_id_different_inputs(self, token_generator):
        """Test HAWK ID varies with different inputs"""
        id1 = token_generator.generate_hawk_id("user1", 0, 1000)
        id2 = token_generator.generate_hawk_id("user2", 0, 1000)
        id3 = token_generator.generate_hawk_id("user1", 1, 1000)
        id4 = token_generator.generate_hawk_id("user1", 0, 2000)

        assert id1 != id2  # Different user
        assert id1 != id3  # Different generation
        assert id1 != id4  # Different expiry

    def test_generate_hawk_key_format(self, token_generator):
        """Test HAWK key is 64-character hex string"""
        hawk_key = token_generator.generate_hawk_key()

        assert len(hawk_key) == 64
        assert re.match(r"^[0-9a-f]{64}$", hawk_key)

    def test_generate_hawk_key_uniqueness(self, token_generator):
        """Test HAWK keys are unique across generations"""
        keys = [token_generator.generate_hawk_key() for _ in range(10)]
        assert len(set(keys)) == 10  # All unique

    def test_generate_uid_consistency(self, token_generator):
        """Test UID is consistent for same user_id"""
        user_id = "user123"

        uid1 = token_generator.generate_uid(user_id)
        uid2 = token_generator.generate_uid(user_id)

        assert uid1 == uid2

    def test_generate_uid_different_users(self, token_generator):
        """Test UID differs for different user_ids"""
        uid1 = token_generator.generate_uid("user1")
        uid2 = token_generator.generate_uid("user2")

        assert uid1 != uid2

    def test_generate_uid_positive(self, token_generator):
        """Test UID is always positive"""
        # Test with various user IDs
        for user_id in ["user1", "test@example.com", "12345", "a" * 100]:
            uid = token_generator.generate_uid(user_id)
            assert uid > 0

    def test_generate_token_returns_token_response(self, token_generator, mock_time):
        """Test generate_token returns TokenResponse with all fields"""
        user_id = "user123"
        generation = 5

        with patch("src.services.token_generator.time.time", return_value=mock_time):
            token = token_generator.generate_token(user_id, generation)

        assert isinstance(token, TokenResponse)
        assert token.id is not None
        assert token.key is not None
        assert token.api_endpoint is not None
        assert token.uid is not None
        assert token.duration == 300
        assert token.hashalg == "sha256"

    def test_generate_token_api_endpoint_format(self, token_generator, base_url, mock_time):
        """Test api_endpoint follows correct format"""
        user_id = "user123"

        with patch("src.services.token_generator.time.time", return_value=mock_time):
            token = token_generator.generate_token(user_id, 0)

        assert token.api_endpoint == f"{base_url}/1.5/{user_id}"

    def test_generate_token_duration(self, token_generator, mock_time):
        """Test token duration is 300 seconds"""
        with patch("src.services.token_generator.time.time", return_value=mock_time):
            token = token_generator.generate_token("user123", 0)

        assert token.duration == 300

    def test_generate_token_hashalg(self, token_generator, mock_time):
        """Test hash algorithm is sha256"""
        with patch("src.services.token_generator.time.time", return_value=mock_time):
            token = token_generator.generate_token("user123", 0)

        assert token.hashalg == "sha256"

    def test_generate_token_hawk_id_contains_expiry(self, token_generator, mock_time):
        """Test HAWK ID contains correct expiry timestamp"""
        user_id = "user123"
        generation = 5
        expected_expiry = mock_time + 300

        with patch("src.services.token_generator.time.time", return_value=mock_time):
            token = token_generator.generate_token(user_id, generation)

        # Decode HAWK ID to verify expiry
        hawk_id = token.id
        padded = hawk_id + "=" * (4 - len(hawk_id) % 4) if len(hawk_id) % 4 else hawk_id
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
        parts = decoded.split(":")

        assert len(parts) == 3
        assert parts[0] == user_id
        assert parts[1] == str(generation)
        assert parts[2] == str(expected_expiry)

    def test_generate_token_uid_matches_generate_uid(self, token_generator, mock_time):
        """Test token UID matches generate_uid output"""
        user_id = "user123"

        with patch("src.services.token_generator.time.time", return_value=mock_time):
            token = token_generator.generate_token(user_id, 0)

        expected_uid = token_generator.generate_uid(user_id)
        assert token.uid == expected_uid

    def test_generate_token_unique_keys(self, token_generator, mock_time):
        """Test each token generation produces unique key"""
        with patch("src.services.token_generator.time.time", return_value=mock_time):
            tokens = [token_generator.generate_token("user123", 0) for _ in range(10)]

        keys = [t.key for t in tokens]
        assert len(set(keys)) == 10  # All unique

    def test_constants(self):
        """Test class constants are correct"""
        assert TokenGenerator.TOKEN_DURATION == 300
        assert TokenGenerator.HASH_ALGORITHM == "sha256"
        assert TokenGenerator.HAWK_KEY_SIZE == 32
