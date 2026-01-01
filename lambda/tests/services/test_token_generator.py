"""Unit tests for TokenGenerator

Tests focus on TokenGenerator orchestration logic:
- Calling HawkService methods correctly
- Constructing api_endpoint properly
- Assembling TokenResponse with correct fields
- Using provided uid parameter

HawkService is mocked - HAWK generation logic is tested in test_hawk_service.py
"""

from unittest.mock import MagicMock

import pytest

from src.services.hawk_service import HawkCredentials
from src.services.token_generator import TokenGenerator
from src.shared.token import TokenResponse


class TestTokenGenerator:
    """Test TokenGenerator orchestration logic with mocked HawkService"""

    @pytest.fixture
    def mock_hawk_service(self):
        """Mock HawkService for testing orchestration"""
        service = MagicMock()
        service.TOKEN_DURATION_SECONDS = 300
        return service

    @pytest.fixture
    def token_generator(self, storage_domain, mock_hawk_service):
        """TokenGenerator instance with mocked HawkService"""
        return TokenGenerator(storage_domain=storage_domain, hawk_service=mock_hawk_service)

    @pytest.fixture
    def mock_hawk_credentials(self):
        """Mock HawkCredentials returned by HawkService"""
        return HawkCredentials(
            user_id="user123",
            generation=5,
            expiry=1702345978,
            hawk_id="dXNlcjEyMzo1OjE3MDIzNDU5Nzg",  # base64 of "user123:5:1702345978"
            hawk_key="a" * 64,  # 64 hex characters
        )

    # ========== UID Generation Tests ==========

    def test_generate_uid_consistency(self, token_generator):
        """Test UID is consistent for same user_id and generation

        Validates: Requirements 4.1, 4.2
        """
        user_id = "user123"
        generation = 0

        uid1 = token_generator.generate_uid(user_id, generation)
        uid2 = token_generator.generate_uid(user_id, generation)

        assert uid1 == uid2

    def test_generate_uid_different_users(self, token_generator):
        """Test UID differs for different user_ids

        Validates: Requirements 4.1, 4.2
        """
        uid1 = token_generator.generate_uid("user1", 0)
        uid2 = token_generator.generate_uid("user2", 0)

        assert uid1 != uid2

    def test_generate_uid_changes_with_generation(self, token_generator):
        """Test UID changes when generation changes (node reset)

        Validates: Requirements 2.4, 4.1
        """
        user_id = "user123"

        uid_gen0 = token_generator.generate_uid(user_id, 0)
        uid_gen1 = token_generator.generate_uid(user_id, 1)
        uid_gen2 = token_generator.generate_uid(user_id, 2)

        # All UIDs should be different
        assert uid_gen0 != uid_gen1
        assert uid_gen1 != uid_gen2
        assert uid_gen0 != uid_gen2

    def test_generate_uid_positive(self, token_generator):
        """Test UID is always positive

        Validates: Requirements 4.1, 4.2
        """
        # Test with various user IDs and generations
        for user_id in ["user1", "test@example.com", "12345", "a" * 100]:
            for generation in [0, 1, 5, 100]:
                uid = token_generator.generate_uid(user_id, generation)
                assert uid > 0

    # ========== Token Generation Orchestration Tests ==========

    # ========== Token Generation Orchestration Tests ==========

    def test_generate_token_calls_hawk_service_correctly(
        self, token_generator, mock_hawk_service, mock_hawk_credentials
    ):
        """Test generate_token calls HawkService.generate_hawk_credentials with correct params

        Validates: Requirements 4.1, 4.2, 4.3, 4.4
        """
        user_id = "user123"
        uid = 123456789
        generation = 5

        mock_hawk_service.generate_hawk_credentials.return_value = mock_hawk_credentials

        token_generator.generate_token(user_id, uid, generation)

        # Verify HawkService was called with correct parameters
        mock_hawk_service.generate_hawk_credentials.assert_called_once_with(user_id, generation)

    def test_generate_token_stores_credentials_in_cache(
        self, token_generator, mock_hawk_service, mock_hawk_credentials
    ):
        """Test generate_token stores credentials via HawkService.store_token_in_cache

        Validates: Requirements 4.1, 4.2, 4.5
        """
        user_id = "user123"
        uid = 123456789
        generation = 5

        mock_hawk_service.generate_hawk_credentials.return_value = mock_hawk_credentials

        token_generator.generate_token(user_id, uid, generation)

        # Verify token was stored in cache
        mock_hawk_service.store_token_in_cache.assert_called_once_with(mock_hawk_credentials)

    def test_generate_token_returns_complete_response(
        self, token_generator, mock_hawk_service, mock_hawk_credentials
    ):
        """Test generate_token returns TokenResponse with all required fields

        Validates: Requirements 1.1, 4.1, 4.2
        """
        user_id = "user123"
        uid = 123456789
        generation = 5

        mock_hawk_service.generate_hawk_credentials.return_value = mock_hawk_credentials

        token = token_generator.generate_token(user_id, uid, generation)

        # Verify response type and all fields present
        assert isinstance(token, TokenResponse)
        assert token.id is not None
        assert token.key is not None
        assert token.api_endpoint is not None
        assert token.uid is not None
        assert token.duration is not None
        assert token.hashalg is not None

    def test_generate_token_uses_hawk_credentials(
        self, token_generator, mock_hawk_service, mock_hawk_credentials
    ):
        """Test generate_token uses HAWK credentials from HawkService

        Validates: Requirements 4.1, 4.2, 4.3, 4.4
        """
        user_id = "user123"
        uid = 123456789
        generation = 5

        mock_hawk_service.generate_hawk_credentials.return_value = mock_hawk_credentials

        token = token_generator.generate_token(user_id, uid, generation)

        # Verify HAWK credentials from HawkService are used
        assert token.id == mock_hawk_credentials.hawk_id
        assert token.key == mock_hawk_credentials.hawk_key

    def test_generate_token_constructs_api_endpoint_correctly(
        self, token_generator, storage_url, mock_hawk_service, mock_hawk_credentials
    ):
        """Test generate_token constructs api_endpoint with correct format

        Validates: Requirements 2.3, 2.5
        """
        user_id = "user123"
        uid = 123456789
        generation = 0

        mock_hawk_service.generate_hawk_credentials.return_value = mock_hawk_credentials

        token = token_generator.generate_token(user_id, uid, generation)

        # Verify api_endpoint format: https://{storage_domain}/1.5/{uid}
        assert token.api_endpoint == f"{storage_url}/1.5/{uid}"

    def test_generate_token_uses_provided_uid(
        self, token_generator, mock_hawk_service, mock_hawk_credentials
    ):
        """Test generate_token uses the uid parameter provided (not generating its own)

        Validates: Requirements 2.1, 4.1
        """
        user_id = "user123"
        uid = 987654321
        generation = 5

        mock_hawk_service.generate_hawk_credentials.return_value = mock_hawk_credentials

        token = token_generator.generate_token(user_id, uid, generation)

        # Verify the exact uid provided is used in response
        assert token.uid == uid

    def test_generate_token_different_uids_different_endpoints(
        self, token_generator, storage_url, mock_hawk_service, mock_hawk_credentials
    ):
        """Test different uids result in different api_endpoints

        Validates: Requirements 2.2, 2.3
        """
        user_id = "user123"
        generation = 0

        mock_hawk_service.generate_hawk_credentials.return_value = mock_hawk_credentials

        token1 = token_generator.generate_token(user_id, 111111, generation)
        token2 = token_generator.generate_token(user_id, 222222, generation)

        # Different uids should produce different endpoints
        assert token1.api_endpoint != token2.api_endpoint
        assert token1.api_endpoint == f"{storage_url}/1.5/111111"
        assert token2.api_endpoint == f"{storage_url}/1.5/222222"

    def test_generate_token_duration_from_hawk_service(
        self, token_generator, mock_hawk_service, mock_hawk_credentials
    ):
        """Test generate_token uses duration from HawkService

        Validates: Requirements 1.5, 4.1
        """
        user_id = "user123"
        uid = 123456789
        generation = 0

        mock_hawk_service.generate_hawk_credentials.return_value = mock_hawk_credentials
        mock_hawk_service.TOKEN_DURATION_SECONDS = 300

        token = token_generator.generate_token(user_id, uid, generation)

        # Verify duration comes from HawkService
        assert token.duration == 300

    def test_generate_token_hashalg_constant(
        self, token_generator, mock_hawk_service, mock_hawk_credentials
    ):
        """Test generate_token always uses sha256 hash algorithm

        Validates: Requirements 4.1, 4.2
        """
        user_id = "user123"
        uid = 123456789
        generation = 0

        mock_hawk_service.generate_hawk_credentials.return_value = mock_hawk_credentials

        token = token_generator.generate_token(user_id, uid, generation)

        # Verify hash algorithm is always sha256
        assert token.hashalg == "sha256"

    # ========== Class Constants Tests ==========

    def test_hash_algorithm_constant(self):
        """Test HASH_ALGORITHM class constant is sha256

        Validates: Requirements 4.1, 4.2
        """
        assert TokenGenerator.HASH_ALGORITHM == "sha256"
