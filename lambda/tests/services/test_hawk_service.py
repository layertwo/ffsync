"""Tests for HawkService"""

import base64
import time
from unittest.mock import MagicMock

import pytest

from src.services.hawk_service import HawkCredentials, HawkService
from src.shared.exceptions import (
    AuthenticationException,
    ExpiredHawkTokenException,
    InvalidGenerationException,
    InvalidHawkHeaderException,
    InvalidHawkSignatureException,
)


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


class TestParseHawkHeader:
    """Tests for parse_hawk_header method"""

    def test_parse_valid_hawk_header(self, hawk_service):
        """Test parsing a valid HAWK header"""
        header = 'Hawk id="abc123", ts="1234567890", nonce="xyz", mac="signature=="'
        result = hawk_service.parse_hawk_header(header)

        assert result["id"] == "abc123"
        assert result["ts"] == "1234567890"
        assert result["nonce"] == "xyz"
        assert result["mac"] == "signature=="

    def test_parse_hawk_header_missing_prefix(self, hawk_service):
        """Test parsing header without 'Hawk ' prefix"""
        header = 'id="abc123", ts="1234567890", nonce="xyz", mac="signature=="'

        with pytest.raises(InvalidHawkHeaderException) as exc_info:
            hawk_service.parse_hawk_header(header)

        assert "must start with 'Hawk '" in str(exc_info.value)

    def test_parse_hawk_header_missing_id(self, hawk_service):
        """Test parsing header missing required 'id' field"""
        header = 'Hawk ts="1234567890", nonce="xyz", mac="signature=="'

        with pytest.raises(InvalidHawkHeaderException) as exc_info:
            hawk_service.parse_hawk_header(header)

        assert "Missing required HAWK parameter: id" in str(exc_info.value)

    def test_parse_hawk_header_missing_ts(self, hawk_service):
        """Test parsing header missing required 'ts' field"""
        header = 'Hawk id="abc123", nonce="xyz", mac="signature=="'

        with pytest.raises(InvalidHawkHeaderException) as exc_info:
            hawk_service.parse_hawk_header(header)

        assert "Missing required HAWK parameter: ts" in str(exc_info.value)

    def test_parse_hawk_header_missing_nonce(self, hawk_service):
        """Test parsing header missing required 'nonce' field"""
        header = 'Hawk id="abc123", ts="1234567890", mac="signature=="'

        with pytest.raises(InvalidHawkHeaderException) as exc_info:
            hawk_service.parse_hawk_header(header)

        assert "Missing required HAWK parameter: nonce" in str(exc_info.value)

    def test_parse_hawk_header_missing_mac(self, hawk_service):
        """Test parsing header missing required 'mac' field"""
        header = 'Hawk id="abc123", ts="1234567890", nonce="xyz"'

        with pytest.raises(InvalidHawkHeaderException) as exc_info:
            hawk_service.parse_hawk_header(header)

        assert "Missing required HAWK parameter: mac" in str(exc_info.value)

    def test_parse_hawk_header_invalid_format(self, hawk_service):
        """Test parsing header with invalid parameter format"""
        header = 'Hawk id="abc123", invalid_param, ts="1234567890"'

        with pytest.raises(InvalidHawkHeaderException) as exc_info:
            hawk_service.parse_hawk_header(header)

        assert "Invalid HAWK parameter" in str(exc_info.value)


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


class TestValidateTimestamp:
    """Tests for validate_timestamp method"""

    def test_validate_timestamp_within_skew(self, hawk_service):
        """Test validation of timestamp within acceptable skew"""
        current_time = int(time.time())

        result = hawk_service.validate_timestamp(current_time)

        assert result is True

    def test_validate_timestamp_past_within_skew(self, hawk_service):
        """Test validation of past timestamp within skew"""
        past_time = int(time.time()) - 30  # 30 seconds ago

        result = hawk_service.validate_timestamp(past_time)

        assert result is True

    def test_validate_timestamp_future_within_skew(self, hawk_service):
        """Test validation of future timestamp within skew"""
        future_time = int(time.time()) + 30  # 30 seconds in future

        result = hawk_service.validate_timestamp(future_time)

        assert result is True

    def test_validate_timestamp_past_exceeds_skew(self, hawk_service):
        """Test validation of past timestamp exceeding skew"""
        past_time = int(time.time()) - 120  # 2 minutes ago (exceeds 60s skew)

        result = hawk_service.validate_timestamp(past_time)

        assert result is False

    def test_validate_timestamp_future_exceeds_skew(self, hawk_service):
        """Test validation of future timestamp exceeding skew"""
        future_time = int(time.time()) + 120  # 2 minutes in future

        result = hawk_service.validate_timestamp(future_time)

        assert result is False


class TestBuildNormalizedString:
    """Tests for build_normalized_string method"""

    def test_build_normalized_string_basic(self, hawk_service):
        """Test building normalized string with basic parameters"""
        result = hawk_service.build_normalized_string(
            timestamp="1234567890",
            nonce="abc123",
            method="GET",
            uri="/storage/bookmarks",
            host="api.example.com",
            port="443",
        )

        expected = (
            "hawk.1.header\n"
            "1234567890\n"
            "abc123\n"
            "GET\n"
            "/storage/bookmarks\n"
            "api.example.com\n"
            "443\n"
            "\n"
            "\n"
        )

        assert result == expected

    def test_build_normalized_string_with_payload_hash(self, hawk_service):
        """Test building normalized string with payload hash"""
        result = hawk_service.build_normalized_string(
            timestamp="1234567890",
            nonce="abc123",
            method="POST",
            uri="/storage/bookmarks",
            host="api.example.com",
            port="443",
            payload_hash="hash123",
        )

        assert "hash123\n" in result

    def test_build_normalized_string_with_ext(self, hawk_service):
        """Test building normalized string with extension data"""
        result = hawk_service.build_normalized_string(
            timestamp="1234567890",
            nonce="abc123",
            method="GET",
            uri="/storage/bookmarks",
            host="api.example.com",
            port="443",
            ext="ext-data",
        )

        assert result.endswith("ext-data\n")

    def test_build_normalized_string_uppercase_method(self, hawk_service):
        """Test that method is converted to uppercase"""
        result = hawk_service.build_normalized_string(
            timestamp="1234567890",
            nonce="abc123",
            method="get",
            uri="/storage/bookmarks",
            host="api.example.com",
            port="443",
        )

        assert "\nGET\n" in result

    def test_build_normalized_string_lowercase_host(self, hawk_service):
        """Test that host is converted to lowercase"""
        result = hawk_service.build_normalized_string(
            timestamp="1234567890",
            nonce="abc123",
            method="GET",
            uri="/storage/bookmarks",
            host="API.EXAMPLE.COM",
            port="443",
        )

        assert "\napi.example.com\n" in result


class TestCalculateMac:
    """Tests for calculate_mac method"""

    def test_calculate_mac_returns_base64(self, hawk_service):
        """Test that MAC calculation returns base64-encoded string"""
        key = "a" * 64  # 64-char hex string
        normalized = "test string"

        result = hawk_service.calculate_mac(key, normalized)

        # Should be base64-encoded
        assert isinstance(result, str)
        # Base64 strings only contain these characters
        assert all(
            c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in result
        )

    def test_calculate_mac_deterministic(self, hawk_service):
        """Test that MAC calculation is deterministic"""
        key = "a" * 64
        normalized = "test string"

        result1 = hawk_service.calculate_mac(key, normalized)
        result2 = hawk_service.calculate_mac(key, normalized)

        assert result1 == result2

    def test_calculate_mac_different_keys(self, hawk_service):
        """Test that different keys produce different MACs"""
        key1 = "a" * 64
        key2 = "b" * 64
        normalized = "test string"

        result1 = hawk_service.calculate_mac(key1, normalized)
        result2 = hawk_service.calculate_mac(key2, normalized)

        assert result1 != result2


class TestVerifyMac:
    """Tests for verify_mac method"""

    def test_verify_mac_valid(self, hawk_service):
        """Test verification of valid MAC"""
        key = "a" * 64
        timestamp = 1234567890
        nonce = "abc123"
        method = "GET"
        uri = "/storage/bookmarks"
        host = "api.example.com"
        port = 443

        # Calculate expected MAC
        normalized = hawk_service.build_normalized_string(
            str(timestamp), nonce, method, uri, host, str(port)
        )
        expected_mac = hawk_service.calculate_mac(key, normalized)

        result = hawk_service.verify_mac(
            key, expected_mac, timestamp, nonce, method, uri, host, port
        )

        assert result is True

    def test_verify_mac_invalid(self, hawk_service):
        """Test verification of invalid MAC"""
        key = "a" * 64
        invalid_mac = "invalid_signature"
        timestamp = 1234567890
        nonce = "abc123"
        method = "GET"
        uri = "/storage/bookmarks"
        host = "api.example.com"
        port = 443

        result = hawk_service.verify_mac(
            key, invalid_mac, timestamp, nonce, method, uri, host, port
        )

        assert result is False

    def test_verify_mac_wrong_key(self, hawk_service):
        """Test verification with wrong key"""
        correct_key = "a" * 64
        wrong_key = "b" * 64
        timestamp = 1234567890
        nonce = "abc123"
        method = "GET"
        uri = "/storage/bookmarks"
        host = "api.example.com"
        port = 443

        # Calculate MAC with correct key
        normalized = hawk_service.build_normalized_string(
            str(timestamp), nonce, method, uri, host, str(port)
        )
        mac = hawk_service.calculate_mac(correct_key, normalized)

        # Verify with wrong key
        result = hawk_service.verify_mac(wrong_key, mac, timestamp, nonce, method, uri, host, port)

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
        from botocore.exceptions import ClientError

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
        timestamp = int(time.time())
        nonce = "abc123"
        method = "GET"
        path = "/storage/bookmarks"
        host = "api.example.com"
        port = 443

        # Calculate valid MAC
        normalized = hawk_service.build_normalized_string(
            str(timestamp), nonce, method, path, host, str(port)
        )
        mac = hawk_service.calculate_mac(hawk_key, normalized)

        # Create HAWK header
        authorization_header = (
            f'Hawk id="{hawk_id}", ts="{timestamp}", nonce="{nonce}", mac="{mac}"'
        )

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

    def test_validate_invalid_timestamp(self, hawk_service):
        """Test validation with invalid timestamp"""
        user_id = "user123"
        generation = 5
        expiry = int(time.time()) + 300
        hawk_id = (
            base64.urlsafe_b64encode(f"{user_id}:{generation}:{expiry}".encode())
            .decode()
            .rstrip("=")
        )
        timestamp = int(time.time()) - 200  # Too far in past
        nonce = "abc123"
        mac = "dummy_mac"

        authorization_header = (
            f'Hawk id="{hawk_id}", ts="{timestamp}", nonce="{nonce}", mac="{mac}"'
        )

        with pytest.raises(InvalidHawkSignatureException) as exc_info:
            hawk_service.validate(
                authorization_header, "GET", "/storage/bookmarks", "api.example.com", 443
            )

        assert "outside acceptable window" in str(exc_info.value)

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
        timestamp = int(time.time())
        nonce = "abc123"
        mac = "dummy_mac"

        authorization_header = (
            f'Hawk id="{hawk_id}", ts="{timestamp}", nonce="{nonce}", mac="{mac}"'
        )

        # Mock DynamoDB response with different generation
        mock_dynamodb_table.get_item.return_value = {
            "Item": {
                "hawk_key": "a" * 64,
                "user_id": user_id,
                "generation": cached_generation,
            }
        }

        with pytest.raises(InvalidGenerationException):
            hawk_service.validate(
                authorization_header, "GET", "/storage/bookmarks", "api.example.com", 443
            )

    def test_validate_invalid_signature(self, hawk_service, mock_dynamodb_table):
        """Test validation with invalid signature"""
        user_id = "user123"
        generation = 5
        expiry = int(time.time()) + 300
        hawk_id = (
            base64.urlsafe_b64encode(f"{user_id}:{generation}:{expiry}".encode())
            .decode()
            .rstrip("=")
        )
        timestamp = int(time.time())
        nonce = "abc123"
        invalid_mac = "invalid_signature"

        authorization_header = (
            f'Hawk id="{hawk_id}", ts="{timestamp}", nonce="{nonce}", mac="{invalid_mac}"'
        )

        # Mock DynamoDB response
        mock_dynamodb_table.get_item.return_value = {
            "Item": {
                "hawk_key": "a" * 64,
                "user_id": user_id,
                "generation": generation,
            }
        }

        with pytest.raises(InvalidHawkSignatureException) as exc_info:
            hawk_service.validate(
                authorization_header, "GET", "/storage/bookmarks", "api.example.com", 443
            )

        assert "MAC verification failed" in str(exc_info.value)


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
