"""Tests for HawkService"""

import base64
import time
from unittest.mock import MagicMock, patch

import mohawk
import mohawk.exc
import pytest
from botocore.exceptions import ClientError

from src.services.hawk_service import HawkCredentials, HawkService
from src.shared.exceptions import (
    AuthenticationException,
    ExpiredHawkTokenException,
    InvalidGenerationException,
    InvalidHawkHeaderException,
    InvalidHawkSignatureException,
)
from tests.fixtures.integration import build_hawk_auth_header


@pytest.fixture
def mock_dynamodb_table():
    """Mock DynamoDB table"""
    table = MagicMock()
    return table


@pytest.fixture
def hawk_service(mock_dynamodb_table):
    """Create HawkService with mocked DynamoDB"""
    service = HawkService(token_cache_table=mock_dynamodb_table)
    return service


class TestHawkServiceInit:
    """Tests for HawkService initialization"""

    def test_init_stores_table(self, hawk_service, mock_dynamodb_table):
        """Test that initialization stores the DynamoDB table"""
        assert hawk_service.token_cache_table is mock_dynamodb_table


class TestExtractHawkId:
    """Tests for _extract_hawk_id method"""

    def test_extract_hawk_id_valid(self, hawk_service):
        """Test extracting id from a valid Hawk header"""
        header = 'Hawk id="abc123", ts="1234567890", nonce="xyz", mac="sig=="'
        result = hawk_service._extract_hawk_id(header)
        assert result == "abc123"

    def test_extract_hawk_id_missing_prefix(self, hawk_service):
        """Test extraction fails when header doesn't start with 'Hawk '"""
        with pytest.raises(InvalidHawkHeaderException, match="must start with 'Hawk '"):
            hawk_service._extract_hawk_id('id="abc123", ts="1234567890"')

    def test_extract_hawk_id_empty_header(self, hawk_service):
        """Test extraction fails for empty header"""
        with pytest.raises(InvalidHawkHeaderException, match="must start with 'Hawk '"):
            hawk_service._extract_hawk_id("")

    def test_extract_hawk_id_none_header(self, hawk_service):
        """Test extraction fails for None header"""
        with pytest.raises(InvalidHawkHeaderException, match="must start with 'Hawk '"):
            hawk_service._extract_hawk_id(None)

    def test_extract_hawk_id_missing_id_field(self, hawk_service):
        """Test extraction fails when id field is missing"""
        with pytest.raises(InvalidHawkHeaderException, match="Missing id"):
            hawk_service._extract_hawk_id('Hawk ts="1234567890", nonce="xyz"')


class TestDecodeHawkId:
    """Tests for decode_hawk_id method"""

    def test_decode_valid_hawk_id(self, hawk_service):
        """Test decoding a valid HAWK ID"""
        # Create a valid HAWK ID: user123:5:1234567890
        hawk_id = base64.urlsafe_b64encode(b"user123:5:1234567890").decode("utf-8").rstrip("=")

        user_id, generation, expiry = hawk_service.decode_hawk_id(hawk_id)

        assert user_id == "user123"
        assert generation == 5
        assert expiry == 1234567890

    def test_decode_hawk_id_with_padding(self, hawk_service):
        """Test decoding HAWK ID that needs padding"""
        # Create HAWK ID with padding
        hawk_id = base64.urlsafe_b64encode(b"user:1:9999").decode("utf-8").rstrip("=")

        user_id, generation, expiry = hawk_service.decode_hawk_id(hawk_id)

        assert user_id == "user"
        assert generation == 1
        assert expiry == 9999

    def test_decode_hawk_id_invalid_parts(self, hawk_service):
        """Test decoding HAWK ID with wrong number of parts"""
        # Create invalid HAWK ID with only 2 parts
        hawk_id = base64.urlsafe_b64encode(b"user123:5").decode("utf-8").rstrip("=")

        with pytest.raises(InvalidHawkHeaderException) as exc_info:
            hawk_service.decode_hawk_id(hawk_id)

        assert "HAWK ID must have 3 parts" in str(exc_info.value)

    def test_decode_hawk_id_invalid_base64(self, hawk_service):
        """Test decoding invalid base64 HAWK ID"""
        hawk_id = "not-valid-base64!!!"

        with pytest.raises(InvalidHawkHeaderException) as exc_info:
            hawk_service.decode_hawk_id(hawk_id)

        assert "Invalid HAWK ID format" in str(exc_info.value)

    def test_decode_hawk_id_invalid_generation(self, hawk_service):
        """Test decoding HAWK ID with non-integer generation"""
        hawk_id = base64.urlsafe_b64encode(b"user:abc:1234567890").decode("utf-8").rstrip("=")

        with pytest.raises(InvalidHawkHeaderException) as exc_info:
            hawk_service.decode_hawk_id(hawk_id)

        assert "Invalid HAWK ID format" in str(exc_info.value)


class TestValidateHawkIdExpiry:
    """Tests for validate_hawk_id_expiry method"""

    def test_validate_expiry_not_expired(self, hawk_service):
        """Test validation of non-expired token"""
        future_expiry = int(time.time()) + 300  # 5 minutes in future

        result = hawk_service.validate_hawk_id_expiry(future_expiry)

        assert result is True

    def test_validate_expiry_expired(self, hawk_service):
        """Test validation of expired token"""
        past_expiry = int(time.time()) - 300  # 5 minutes in past

        result = hawk_service.validate_hawk_id_expiry(past_expiry)

        assert result is False

    def test_validate_expiry_at_boundary(self, hawk_service):
        """Test validation at expiry boundary"""
        current_time = int(time.time())

        result = hawk_service.validate_hawk_id_expiry(current_time)

        # Should be False since current_time is not < current_time
        assert result is False


class TestGetHawkKeyFromCache:
    """Tests for get_hawk_key_from_cache method"""

    def test_get_hawk_key_success(self, hawk_service, mock_dynamodb_table):
        """Test successful retrieval of HAWK key from cache"""
        hawk_id = "test_hawk_id"
        mock_dynamodb_table.get_item.return_value = {
            "Item": {
                "hawk_key": "a" * 64,
                "user_id": "user123",
                "generation": 5,
            }
        }

        hawk_key, user_id, generation = hawk_service.get_hawk_key_from_cache(hawk_id)

        assert hawk_key == "a" * 64
        assert user_id == "user123"
        assert generation == 5
        mock_dynamodb_table.get_item.assert_called_once_with(Key={"PK": f"TOKEN#{hawk_id}"})

    def test_get_hawk_key_not_found(self, hawk_service, mock_dynamodb_table):
        """Test retrieval when token not found in cache"""
        hawk_id = "nonexistent_hawk_id"
        mock_dynamodb_table.get_item.return_value = {}

        with pytest.raises(AuthenticationException) as exc_info:
            hawk_service.get_hawk_key_from_cache(hawk_id)

        assert "HAWK token not found" in str(exc_info.value)

    def test_get_hawk_key_dynamodb_error(self, hawk_service, mock_dynamodb_table):
        """Test retrieval when DynamoDB error occurs"""
        hawk_id = "test_hawk_id"
        mock_dynamodb_table.get_item.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailable", "Message": "Service unavailable"}},
            "GetItem",
        )

        with pytest.raises(AuthenticationException) as exc_info:
            hawk_service.get_hawk_key_from_cache(hawk_id)

        assert "Failed to retrieve HAWK token" in str(exc_info.value)


class TestValidate:
    """Tests for validate method (full validation flow)"""

    def test_validate_success(self, hawk_service, mock_dynamodb_table):
        """Test successful HAWK validation"""
        # Create valid HAWK credentials
        user_id = "user123"
        generation = 5
        expiry = int(time.time()) + 300
        hawk_id = (
            base64.urlsafe_b64encode(f"{user_id}:{generation}:{expiry}".encode())
            .decode()
            .rstrip("=")
        )
        hawk_key = "a" * 64
        method = "GET"
        path = "/storage/bookmarks"
        host = "api.example.com"
        port = 443

        # Build header using mohawk.Sender
        authorization_header = build_hawk_auth_header(hawk_id, hawk_key, method, path, host, port)

        # Mock DynamoDB response
        mock_dynamodb_table.get_item.return_value = {
            "Item": {
                "hawk_key": hawk_key,
                "user_id": user_id,
                "generation": generation,
            }
        }

        # Validate
        credentials = hawk_service.validate(authorization_header, method, path, host, port)

        assert credentials.user_id == user_id
        assert credentials.generation == generation
        assert credentials.expiry == expiry
        assert credentials.hawk_id == hawk_id

    def test_validate_expired_token(self, hawk_service):
        """Test validation with expired token"""
        user_id = "user123"
        generation = 5
        expiry = int(time.time()) - 300  # Expired 5 minutes ago
        hawk_id = (
            base64.urlsafe_b64encode(f"{user_id}:{generation}:{expiry}".encode())
            .decode()
            .rstrip("=")
        )
        timestamp = int(time.time())
        nonce = "abc123"
        mac = "dummy_mac"

        authorization_header = (
            f'Hawk id="{hawk_id}", ts="{timestamp}", nonce="{nonce}", mac="{mac}"'
        )

        with pytest.raises(ExpiredHawkTokenException):
            hawk_service.validate(
                authorization_header, "GET", "/storage/bookmarks", "api.example.com", 443
            )

    def test_validate_generation_mismatch(self, hawk_service, mock_dynamodb_table):
        """Test validation with generation mismatch"""
        user_id = "user123"
        generation = 5
        cached_generation = 6  # Different generation in cache
        expiry = int(time.time()) + 300
        hawk_id = (
            base64.urlsafe_b64encode(f"{user_id}:{generation}:{expiry}".encode())
            .decode()
            .rstrip("=")
        )
        hawk_key = "a" * 64
        method = "GET"
        path = "/storage/bookmarks"
        host = "api.example.com"
        port = 443

        # Build a valid header (MAC will be valid, but generation will mismatch)
        authorization_header = build_hawk_auth_header(hawk_id, hawk_key, method, path, host, port)

        # Mock DynamoDB response with different generation
        mock_dynamodb_table.get_item.return_value = {
            "Item": {
                "hawk_key": hawk_key,
                "user_id": user_id,
                "generation": cached_generation,
            }
        }

        with pytest.raises(InvalidGenerationException):
            hawk_service.validate(authorization_header, method, path, host, port)

    def test_validate_invalid_mac(self, hawk_service, mock_dynamodb_table):
        """Test validation with invalid MAC (wrong key)"""
        user_id = "user123"
        generation = 5
        expiry = int(time.time()) + 300
        hawk_id = (
            base64.urlsafe_b64encode(f"{user_id}:{generation}:{expiry}".encode())
            .decode()
            .rstrip("=")
        )
        wrong_key = "b" * 64
        correct_key = "a" * 64
        method = "GET"
        path = "/storage/bookmarks"
        host = "api.example.com"
        port = 443

        # Build header with the wrong key
        authorization_header = build_hawk_auth_header(hawk_id, wrong_key, method, path, host, port)

        # Mock DynamoDB response with the correct key (different from what was used to sign)
        mock_dynamodb_table.get_item.return_value = {
            "Item": {
                "hawk_key": correct_key,
                "user_id": user_id,
                "generation": generation,
            }
        }

        with pytest.raises(InvalidHawkSignatureException, match="MAC verification failed"):
            hawk_service.validate(authorization_header, method, path, host, port)

    def test_validate_timestamp_outside_skew(self, hawk_service, mock_dynamodb_table):
        """Test validation with timestamp outside acceptable window"""
        user_id = "user123"
        generation = 5
        expiry = int(time.time()) + 300
        hawk_id = (
            base64.urlsafe_b64encode(f"{user_id}:{generation}:{expiry}".encode())
            .decode()
            .rstrip("=")
        )
        hawk_key = "a" * 64
        method = "GET"
        path = "/storage/bookmarks"
        host = "api.example.com"
        port = 443

        # Build header with an old timestamp (200 seconds in the past, exceeding 60s skew)
        old_ts = int(time.time()) - 200
        authorization_header = build_hawk_auth_header(
            hawk_id, hawk_key, method, path, host, port, _timestamp=old_ts
        )

        # Mock DynamoDB response
        mock_dynamodb_table.get_item.return_value = {
            "Item": {
                "hawk_key": hawk_key,
                "user_id": user_id,
                "generation": generation,
            }
        }

        with pytest.raises(InvalidHawkSignatureException, match="outside acceptable window"):
            hawk_service.validate(authorization_header, method, path, host, port)

    def test_validate_token_not_in_cache(self, hawk_service, mock_dynamodb_table):
        """Test validation when token is not found in DynamoDB cache"""
        user_id = "user123"
        generation = 5
        expiry = int(time.time()) + 300
        hawk_id = (
            base64.urlsafe_b64encode(f"{user_id}:{generation}:{expiry}".encode())
            .decode()
            .rstrip("=")
        )
        hawk_key = "a" * 64
        method = "GET"
        path = "/storage/bookmarks"
        host = "api.example.com"
        port = 443

        authorization_header = build_hawk_auth_header(hawk_id, hawk_key, method, path, host, port)

        # Token not found in cache
        mock_dynamodb_table.get_item.return_value = {}

        with pytest.raises(AuthenticationException, match="HAWK token not found"):
            hawk_service.validate(authorization_header, method, path, host, port)

    def test_validate_dynamodb_error(self, hawk_service, mock_dynamodb_table):
        """Test validation when DynamoDB raises an error"""
        user_id = "user123"
        generation = 5
        expiry = int(time.time()) + 300
        hawk_id = (
            base64.urlsafe_b64encode(f"{user_id}:{generation}:{expiry}".encode())
            .decode()
            .rstrip("=")
        )
        hawk_key = "a" * 64
        method = "GET"
        path = "/storage/bookmarks"
        host = "api.example.com"
        port = 443

        authorization_header = build_hawk_auth_header(hawk_id, hawk_key, method, path, host, port)

        # DynamoDB error
        mock_dynamodb_table.get_item.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailable", "Message": "Service unavailable"}},
            "GetItem",
        )

        with pytest.raises(AuthenticationException, match="Failed to retrieve HAWK token"):
            hawk_service.validate(authorization_header, method, path, host, port)

    def test_validate_missing_header(self, hawk_service):
        """Test validation with missing authorization header"""
        with pytest.raises(InvalidHawkHeaderException, match="must start with 'Hawk '"):
            hawk_service.validate("", "GET", "/storage/bookmarks", "api.example.com", 443)

    def test_validate_malformed_header(self, hawk_service):
        """Test validation with malformed header (no Hawk prefix)"""
        with pytest.raises(InvalidHawkHeaderException, match="must start with 'Hawk '"):
            hawk_service.validate(
                "Bearer token123", "GET", "/storage/bookmarks", "api.example.com", 443
            )

    def test_validate_bad_header_value(self, hawk_service, mock_dynamodb_table):
        """Test validation with malformed Hawk header content (BadHeaderValue)"""
        user_id = "user123"
        generation = 5
        expiry = int(time.time()) + 300
        hawk_id = (
            base64.urlsafe_b64encode(f"{user_id}:{generation}:{expiry}".encode())
            .decode()
            .rstrip("=")
        )

        # Header with an unparseable trailing field triggers BadHeaderValue in mohawk
        authorization_header = f'Hawk id="{hawk_id}", ts="12345", nonce="n", mac="m", bad'

        # Mock DynamoDB response (credentials_map needs to work)
        mock_dynamodb_table.get_item.return_value = {
            "Item": {
                "hawk_key": "a" * 64,
                "user_id": user_id,
                "generation": generation,
            }
        }

        with pytest.raises(InvalidHawkHeaderException):
            hawk_service.validate(
                authorization_header, "GET", "/storage/bookmarks", "api.example.com", 443
            )

    def test_validate_missing_authorization_from_mohawk(self, hawk_service, mock_dynamodb_table):
        """Test MissingAuthorization exception path from mohawk.Receiver"""
        user_id = "user123"
        generation = 5
        expiry = int(time.time()) + 300
        hawk_id = (
            base64.urlsafe_b64encode(f"{user_id}:{generation}:{expiry}".encode())
            .decode()
            .rstrip("=")
        )
        hawk_key = "a" * 64

        authorization_header = build_hawk_auth_header(
            hawk_id, hawk_key, "GET", "/storage/bookmarks", "api.example.com", 443
        )

        mock_dynamodb_table.get_item.return_value = {
            "Item": {
                "hawk_key": hawk_key,
                "user_id": user_id,
                "generation": generation,
            }
        }

        with patch("src.services.hawk_service.mohawk.Receiver") as mock_receiver:
            mock_receiver.side_effect = mohawk.exc.MissingAuthorization()
            with pytest.raises(InvalidHawkHeaderException, match="Missing authorization"):
                hawk_service.validate(
                    authorization_header, "GET", "/storage/bookmarks", "api.example.com", 443
                )

    def test_validate_generic_hawk_fail(self, hawk_service, mock_dynamodb_table):
        """Test generic HawkFail catch-all exception path"""
        user_id = "user123"
        generation = 5
        expiry = int(time.time()) + 300
        hawk_id = (
            base64.urlsafe_b64encode(f"{user_id}:{generation}:{expiry}".encode())
            .decode()
            .rstrip("=")
        )
        hawk_key = "a" * 64

        authorization_header = build_hawk_auth_header(
            hawk_id, hawk_key, "GET", "/storage/bookmarks", "api.example.com", 443
        )

        mock_dynamodb_table.get_item.return_value = {
            "Item": {
                "hawk_key": hawk_key,
                "user_id": user_id,
                "generation": generation,
            }
        }

        with patch("src.services.hawk_service.mohawk.Receiver") as mock_receiver:
            mock_receiver.side_effect = mohawk.exc.InvalidCredentials("bad creds")
            with pytest.raises(InvalidHawkSignatureException, match="bad creds"):
                hawk_service.validate(
                    authorization_header, "GET", "/storage/bookmarks", "api.example.com", 443
                )

    def test_validate_rejects_replayed_nonce(self, hawk_service, mock_dynamodb_table):
        """Replayed nonce is rejected"""
        user_id = "user1"
        generation = 0
        expiry = int(time.time()) + 300
        hawk_id = hawk_service.generate_hawk_id(user_id, generation, expiry)
        hawk_key = hawk_service.generate_hawk_key()
        mock_dynamodb_table.get_item.return_value = {
            "Item": {"hawk_key": hawk_key, "user_id": user_id, "generation": generation}
        }
        # Nonce already seen -- put_item raises ConditionalCheckFailedException
        mock_dynamodb_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}},
            "PutItem",
        )
        header = build_hawk_auth_header(hawk_id, hawk_key, "GET", "/test", "host", 443)
        with pytest.raises(InvalidHawkSignatureException):
            hawk_service.validate(header, "GET", "/test", "host", 443)


class TestSeenNonce:
    """Tests for _seen_nonce method"""

    def test_seen_nonce_new_nonce(self, hawk_service, mock_dynamodb_table):
        """New nonce returns False (not seen before)"""
        mock_dynamodb_table.put_item.return_value = {}
        result = hawk_service._seen_nonce("sender1", "nonce1", "12345")
        assert result is False
        mock_dynamodb_table.put_item.assert_called_once()

    def test_seen_nonce_replay_detected(self, hawk_service, mock_dynamodb_table):
        """Replayed nonce returns True"""
        mock_dynamodb_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": ""}},
            "PutItem",
        )
        result = hawk_service._seen_nonce("sender1", "nonce1", "12345")
        assert result is True

    def test_seen_nonce_reraises_other_errors(self, hawk_service, mock_dynamodb_table):
        """Non-conditional errors are re-raised"""
        mock_dynamodb_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "InternalServerError", "Message": "Server error"}},
            "PutItem",
        )
        with pytest.raises(ClientError) as exc_info:
            hawk_service._seen_nonce("sender1", "nonce1", "12345")
        assert exc_info.value.response["Error"]["Code"] == "InternalServerError"


class TestGenerateHawkCredentials:
    """Tests for generate_hawk_credentials method"""

    def test_generate_hawk_credentials(self, hawk_service):
        """Test generation of HAWK credentials"""
        user_id = "user123"
        generation = 5

        credentials = hawk_service.generate_hawk_credentials(user_id, generation)

        assert credentials.user_id == user_id
        assert credentials.generation == generation
        assert credentials.hawk_id is not None
        assert credentials.hawk_key is not None
        assert len(credentials.hawk_key) == 64  # 32 bytes as hex = 64 chars
        assert credentials.expiry > int(time.time())

    def test_generate_hawk_credentials_expiry(self, hawk_service):
        """Test that generated credentials have correct expiry"""
        user_id = "user123"
        generation = 5
        before_time = int(time.time())

        credentials = hawk_service.generate_hawk_credentials(user_id, generation)

        after_time = int(time.time())

        # Expiry should be approximately current_time + 300
        assert credentials.expiry >= before_time + 300
        assert credentials.expiry <= after_time + 300


class TestGenerateHawkId:
    """Tests for generate_hawk_id method"""

    def test_generate_hawk_id_format(self, hawk_service):
        """Test HAWK ID generation format"""
        user_id = "user123"
        generation = 5
        expiry = 1234567890

        hawk_id = hawk_service.generate_hawk_id(user_id, generation, expiry)

        # Should be base64-encoded without padding
        assert isinstance(hawk_id, str)
        assert "=" not in hawk_id

        # Should be decodable
        decoded = base64.urlsafe_b64decode(hawk_id + "==").decode("utf-8")
        assert decoded == f"{user_id}:{generation}:{expiry}"

    def test_generate_hawk_id_different_inputs(self, hawk_service):
        """Test that different inputs produce different HAWK IDs"""
        hawk_id1 = hawk_service.generate_hawk_id("user1", 1, 1000)
        hawk_id2 = hawk_service.generate_hawk_id("user2", 1, 1000)
        hawk_id3 = hawk_service.generate_hawk_id("user1", 2, 1000)

        assert hawk_id1 != hawk_id2
        assert hawk_id1 != hawk_id3


class TestGenerateHawkKey:
    """Tests for generate_hawk_key method"""

    def test_generate_hawk_key_format(self, hawk_service):
        """Test HAWK key generation format"""
        hawk_key = hawk_service.generate_hawk_key()

        # Should be 64-character hex string
        assert len(hawk_key) == 64
        assert all(c in "0123456789abcdef" for c in hawk_key)

    def test_generate_hawk_key_uniqueness(self, hawk_service):
        """Test that generated keys are unique"""
        key1 = hawk_service.generate_hawk_key()
        key2 = hawk_service.generate_hawk_key()

        assert key1 != key2


class TestStoreTokenInCache:
    """Tests for store_token_in_cache method"""

    def test_store_token_in_cache(self, hawk_service, mock_dynamodb_table):
        """Test storing token in cache"""
        credentials = HawkCredentials(
            user_id="user123",
            generation=5,
            expiry=1234567890,
            hawk_id="test_hawk_id",
            hawk_key="a" * 64,
        )

        hawk_service.store_token_in_cache(credentials)

        # Verify put_item was called with correct parameters
        mock_dynamodb_table.put_item.assert_called_once()
        call_args = mock_dynamodb_table.put_item.call_args[1]
        item = call_args["Item"]

        assert item["PK"] == "TOKEN#test_hawk_id"
        assert item["hawk_key"] == "a" * 64
        assert item["user_id"] == "user123"
        assert item["generation"] == 5
        assert item["expiry"] == 1234567890
        assert "created_at" in item


class TestHawkCredentialsDataclass:
    """Tests for HawkCredentials dataclass"""

    def test_hawk_credentials_creation(self):
        """Test creating HawkCredentials"""
        credentials = HawkCredentials(
            user_id="user123",
            generation=5,
            expiry=1234567890,
            hawk_id="test_hawk_id",
            hawk_key="a" * 64,
        )

        assert credentials.user_id == "user123"
        assert credentials.generation == 5
        assert credentials.expiry == 1234567890
        assert credentials.hawk_id == "test_hawk_id"
        assert credentials.hawk_key == "a" * 64

    def test_hawk_credentials_optional_key(self):
        """Test HawkCredentials with optional hawk_key"""
        credentials = HawkCredentials(
            user_id="user123",
            generation=5,
            expiry=1234567890,
            hawk_id="test_hawk_id",
        )

        assert credentials.hawk_key is None
