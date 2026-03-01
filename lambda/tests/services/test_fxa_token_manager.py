"""Unit tests for FxATokenManager with DynamoDB stubber"""

from unittest.mock import patch

import pytest
from botocore.stub import ANY

from src.services import fxa_crypto
from src.services.fxa_token_manager import (
    KEY_FETCH_TOKEN_INFO,
    SESSION_TOKEN_INFO,
    FxATokenManager,
)
from tests.fixtures.integration import build_hawk_auth_header as build_hawk_header


class TestCreateSessionToken:
    """Tests for create_session_token method"""

    @pytest.fixture
    def manager(self, dynamodb_table):
        return FxATokenManager(table=dynamodb_table)

    @pytest.fixture
    def sample_uid(self):
        return "abcdef1234567890abcdef1234567890"

    @pytest.fixture
    def fixed_token(self):
        return b"\xaa" * 32

    @pytest.fixture
    def mock_time(self):
        with patch("src.services.fxa_token_manager.time") as mock:
            mock.time.return_value = 1000000.0
            yield mock

    def test_returns_32_byte_raw_token(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        fixed_token,
        mock_time,
    ):
        """create_session_token returns the 32-byte raw token"""
        with patch("src.services.fxa_token_manager.fxa_crypto") as mock_crypto:
            mock_crypto.generate_random_bytes.return_value = fixed_token
            token_id = fxa_crypto.derive_token_id(fixed_token, SESSION_TOKEN_INFO)
            req_hmac_key = fxa_crypto.derive_req_hmac_key(fixed_token, SESSION_TOKEN_INFO)
            mock_crypto.derive_token_id.return_value = token_id
            mock_crypto.derive_req_hmac_key.return_value = req_hmac_key
            token_id_hex = token_id.hex()

            dynamodb_stubber.add_response(
                "put_item",
                {},
                {
                    "TableName": storage_table_name,
                    "Item": {
                        "PK": f"SESSION#{token_id_hex}",
                        "uid": sample_uid,
                        "verified": True,
                        "createdAt": 1000000000,
                        "expiry": 1000000 + 2592000,
                        "reqHMACkey": req_hmac_key.hex(),
                    },
                },
            )

            result = manager.create_session_token(sample_uid)

        assert result == fixed_token
        assert len(result) == 32
        assert isinstance(result, bytes)

    def test_stores_session_record_in_dynamodb(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        fixed_token,
        mock_time,
    ):
        """create_session_token stores a SESSION# record with correct fields"""
        with patch("src.services.fxa_token_manager.fxa_crypto") as mock_crypto:
            mock_crypto.generate_random_bytes.return_value = fixed_token
            token_id = fxa_crypto.derive_token_id(fixed_token, SESSION_TOKEN_INFO)
            req_hmac_key = fxa_crypto.derive_req_hmac_key(fixed_token, SESSION_TOKEN_INFO)
            mock_crypto.derive_token_id.return_value = token_id
            mock_crypto.derive_req_hmac_key.return_value = req_hmac_key
            token_id_hex = token_id.hex()

            dynamodb_stubber.add_response(
                "put_item",
                {},
                {
                    "TableName": storage_table_name,
                    "Item": {
                        "PK": f"SESSION#{token_id_hex}",
                        "uid": sample_uid,
                        "verified": True,
                        "createdAt": 1000000000,
                        "expiry": 1000000 + 2592000,
                        "reqHMACkey": req_hmac_key.hex(),
                    },
                },
            )

            manager.create_session_token(sample_uid)

        dynamodb_stubber.assert_no_pending_responses()


class TestVerifySessionTokenId:
    """Tests for verify_session_token_id method"""

    @pytest.fixture
    def manager(self, dynamodb_table):
        return FxATokenManager(table=dynamodb_table)

    @pytest.fixture
    def sample_uid(self):
        return "abcdef1234567890abcdef1234567890"

    @pytest.fixture
    def mock_time(self):
        with patch("src.services.fxa_token_manager.time") as mock:
            mock.time.return_value = 1000000.0
            yield mock

    def test_returns_uid_for_valid_token(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_session_token_id returns uid when SESSION# record exists and not expired"""
        token_id_hex = "aa" * 32

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"SESSION#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "verified": {"BOOL": True},
                    "createdAt": {"N": "1000000000"},
                    "expiry": {"N": "1002592000"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"SESSION#{token_id_hex}"},
            },
        )

        result = manager.verify_session_token_id(token_id_hex)

        assert result == sample_uid

    def test_returns_none_for_unknown_token(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """verify_session_token_id returns None when token not found"""
        token_id_hex = "bb" * 32

        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"SESSION#{token_id_hex}"},
            },
        )

        result = manager.verify_session_token_id(token_id_hex)

        assert result is None

    def test_returns_none_for_expired_token(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_session_token_id returns None when token is expired"""
        token_id_hex = "aa" * 32

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"SESSION#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "verified": {"BOOL": True},
                    "createdAt": {"N": "999000000"},
                    "expiry": {"N": "999999"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"SESSION#{token_id_hex}"},
            },
        )

        result = manager.verify_session_token_id(token_id_hex)

        assert result is None


class TestCreateKeyFetchToken:
    """Tests for create_key_fetch_token method"""

    @pytest.fixture
    def manager(self, dynamodb_table):
        return FxATokenManager(table=dynamodb_table)

    @pytest.fixture
    def sample_uid(self):
        return "abcdef1234567890abcdef1234567890"

    @pytest.fixture
    def fixed_token(self):
        return b"\xcc" * 32

    @pytest.fixture
    def mock_time(self):
        with patch("src.services.fxa_token_manager.time") as mock:
            mock.time.return_value = 1000000.0
            yield mock

    def test_returns_32_byte_raw_token(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        fixed_token,
        mock_time,
    ):
        """create_key_fetch_token returns the 32-byte raw token"""
        with patch("src.services.fxa_token_manager.fxa_crypto") as mock_crypto:
            mock_crypto.generate_random_bytes.return_value = fixed_token
            token_id = fxa_crypto.derive_token_id(fixed_token, KEY_FETCH_TOKEN_INFO)
            req_hmac_key = fxa_crypto.derive_req_hmac_key(fixed_token, KEY_FETCH_TOKEN_INFO)
            mock_crypto.derive_token_id.return_value = token_id
            mock_crypto.derive_req_hmac_key.return_value = req_hmac_key
            token_id_hex = token_id.hex()

            dynamodb_stubber.add_response(
                "put_item",
                {},
                {
                    "TableName": storage_table_name,
                    "Item": {
                        "PK": f"KEYFETCH#{token_id_hex}",
                        "uid": sample_uid,
                        "keyFetchToken": fixed_token.hex(),
                        "reqHMACkey": req_hmac_key.hex(),
                        "expiry": 1000000 + 300,
                    },
                },
            )

            result = manager.create_key_fetch_token(sample_uid)

        assert result == fixed_token
        assert len(result) == 32
        assert isinstance(result, bytes)

    def test_stores_keyfetch_record_with_raw_token_hex(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        fixed_token,
        mock_time,
    ):
        """create_key_fetch_token stores a KEYFETCH# record with the raw token hex"""
        with patch("src.services.fxa_token_manager.fxa_crypto") as mock_crypto:
            mock_crypto.generate_random_bytes.return_value = fixed_token
            token_id = fxa_crypto.derive_token_id(fixed_token, KEY_FETCH_TOKEN_INFO)
            req_hmac_key = fxa_crypto.derive_req_hmac_key(fixed_token, KEY_FETCH_TOKEN_INFO)
            mock_crypto.derive_token_id.return_value = token_id
            mock_crypto.derive_req_hmac_key.return_value = req_hmac_key
            token_id_hex = token_id.hex()

            dynamodb_stubber.add_response(
                "put_item",
                {},
                {
                    "TableName": storage_table_name,
                    "Item": {
                        "PK": f"KEYFETCH#{token_id_hex}",
                        "uid": sample_uid,
                        "keyFetchToken": fixed_token.hex(),
                        "reqHMACkey": req_hmac_key.hex(),
                        "expiry": 1000000 + 300,
                    },
                },
            )

            manager.create_key_fetch_token(sample_uid)

        dynamodb_stubber.assert_no_pending_responses()


class TestConsumeKeyFetchToken:
    """Tests for consume_key_fetch_token method (atomic delete)"""

    @pytest.fixture
    def manager(self, dynamodb_table):
        return FxATokenManager(table=dynamodb_table)

    @pytest.fixture
    def sample_uid(self):
        return "abcdef1234567890abcdef1234567890"

    @pytest.fixture
    def mock_time(self):
        with patch("src.services.fxa_token_manager.time") as mock:
            mock.time.return_value = 1000000.0
            yield mock

    def test_returns_uid_and_key_fetch_token(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """consume_key_fetch_token returns dict with uid and keyFetchToken"""
        token_id_hex = "dd" * 32
        raw_token_hex = "cc" * 32

        # Stub atomic delete_item with ReturnValues
        dynamodb_stubber.add_response(
            "delete_item",
            {
                "Attributes": {
                    "PK": {"S": f"KEYFETCH#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "keyFetchToken": {"S": raw_token_hex},
                    "expiry": {"N": "1000300"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"KEYFETCH#{token_id_hex}"},
                "ReturnValues": "ALL_OLD",
                "ConditionExpression": "attribute_exists(PK)",
            },
        )

        result = manager.consume_key_fetch_token(token_id_hex)

        assert result is not None
        assert result["uid"] == sample_uid
        assert result["keyFetchToken"] == raw_token_hex

    def test_returns_none_for_unknown_token(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """consume_key_fetch_token returns None for unknown token (ConditionalCheckFailed)"""
        token_id_hex = "ee" * 32

        dynamodb_stubber.add_client_error(
            "delete_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="The conditional request failed",
        )

        result = manager.consume_key_fetch_token(token_id_hex)

        assert result is None

    def test_returns_none_for_expired_token(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """consume_key_fetch_token returns None when token is expired"""
        token_id_hex = "dd" * 32
        raw_token_hex = "cc" * 32

        dynamodb_stubber.add_response(
            "delete_item",
            {
                "Attributes": {
                    "PK": {"S": f"KEYFETCH#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "keyFetchToken": {"S": raw_token_hex},
                    "expiry": {"N": "999999"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"KEYFETCH#{token_id_hex}"},
                "ReturnValues": "ALL_OLD",
                "ConditionExpression": "attribute_exists(PK)",
            },
        )

        result = manager.consume_key_fetch_token(token_id_hex)

        assert result is None


class TestConsumeKeyFetchTokenEdgeCases:
    """Edge case tests for consume_key_fetch_token"""

    @pytest.fixture
    def manager(self, dynamodb_table):
        return FxATokenManager(table=dynamodb_table)

    def test_reraises_non_conditional_error(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """consume_key_fetch_token re-raises non-ConditionalCheckFailed errors"""
        from botocore.exceptions import ClientError

        token_id_hex = "ee" * 32

        dynamodb_stubber.add_client_error(
            "delete_item",
            service_error_code="InternalServerError",
            service_message="Internal server error",
        )

        with pytest.raises(ClientError) as exc_info:
            manager.consume_key_fetch_token(token_id_hex)
        assert exc_info.value.response["Error"]["Code"] == "InternalServerError"

    @pytest.fixture
    def mock_time(self):
        with patch("src.services.fxa_token_manager.time") as mock:
            mock.time.return_value = 1000000.0
            yield mock

    def test_returns_none_for_empty_attributes(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        mock_time,
    ):
        """consume_key_fetch_token returns None when Attributes is empty"""
        token_id_hex = "ee" * 32

        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"KEYFETCH#{token_id_hex}"},
                "ReturnValues": "ALL_OLD",
                "ConditionExpression": "attribute_exists(PK)",
            },
        )

        result = manager.consume_key_fetch_token(token_id_hex)
        assert result is None


class TestVerifySessionHawk:
    """Tests for verify_session_hawk method"""

    @pytest.fixture
    def manager(self, dynamodb_table):
        return FxATokenManager(table=dynamodb_table)

    @pytest.fixture
    def sample_uid(self):
        return "abcdef1234567890abcdef1234567890"

    @pytest.fixture
    def mock_time(self):
        with patch("src.services.fxa_token_manager.time") as mock:
            mock.time.return_value = 1000000.0
            yield mock

    def test_returns_uid_for_valid_hawk(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_session_hawk returns uid when HMAC is valid"""
        token_id_hex = "aa" * 32
        req_hmac_key_hex = "bb" * 32

        auth_header = build_hawk_header(
            token_id_hex,
            bytes.fromhex(req_hmac_key_hex),
            "GET",
            "/v1/session/status",
            "localhost",
            "443",
        )

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"SESSION#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "verified": {"BOOL": True},
                    "expiry": {"N": "1002592000"},
                    "reqHMACkey": {"S": req_hmac_key_hex},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"SESSION#{token_id_hex}"},
            },
        )

        # Nonce replay protection: put_item for nonce record
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": ANY,
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        result = manager.verify_session_hawk(
            auth_header, "GET", "/v1/session/status", "localhost", "443"
        )

        assert result == sample_uid

    def test_returns_none_for_invalid_mac(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_session_hawk returns None when HMAC does not match"""
        token_id_hex = "aa" * 32
        req_hmac_key_hex = "bb" * 32

        # Build header with wrong mac
        auth_header = f'Hawk id="{token_id_hex}", ts="1000000", nonce="abc", mac="AAAA"'

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"SESSION#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "verified": {"BOOL": True},
                    "expiry": {"N": "1002592000"},
                    "reqHMACkey": {"S": req_hmac_key_hex},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"SESSION#{token_id_hex}"},
            },
        )

        result = manager.verify_session_hawk(
            auth_header, "GET", "/v1/session/status", "localhost", "443"
        )

        assert result is None

    def test_returns_none_for_missing_header(self, manager):
        """verify_session_hawk returns None when header is empty"""
        result = manager.verify_session_hawk("", "GET", "/path", "host", "443")
        assert result is None

    def test_returns_none_for_expired_session(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_session_hawk returns None when session is expired"""
        token_id_hex = "aa" * 32
        req_hmac_key_hex = "bb" * 32

        auth_header = build_hawk_header(
            token_id_hex,
            bytes.fromhex(req_hmac_key_hex),
            "GET",
            "/v1/session/status",
            "localhost",
            "443",
        )

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"SESSION#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "verified": {"BOOL": True},
                    "expiry": {"N": "999999"},
                    "reqHMACkey": {"S": req_hmac_key_hex},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"SESSION#{token_id_hex}"},
            },
        )

        result = manager.verify_session_hawk(
            auth_header, "GET", "/v1/session/status", "localhost", "443"
        )

        assert result is None

    def test_returns_none_for_unknown_session(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        mock_time,
    ):
        """verify_session_hawk returns None when session record not found"""
        token_id_hex = "aa" * 32
        auth_header = f'Hawk id="{token_id_hex}", ts="1000000", nonce="abc", mac="AAAA"'

        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"SESSION#{token_id_hex}"},
            },
        )

        result = manager.verify_session_hawk(auth_header, "GET", "/path", "host", "443")
        assert result is None

    def test_returns_none_for_missing_hmac_key(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_session_hawk returns None when reqHMACkey is missing"""
        token_id_hex = "aa" * 32
        auth_header = f'Hawk id="{token_id_hex}", ts="1000000", nonce="abc", mac="AAAA"'

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"SESSION#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "expiry": {"N": "1002592000"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"SESSION#{token_id_hex}"},
            },
        )

        result = manager.verify_session_hawk(auth_header, "GET", "/path", "host", "443")
        assert result is None

    def test_returns_uid_for_post_request(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_session_hawk returns uid for POST requests (no content hash needed)"""
        token_id_hex = "aa" * 32
        req_hmac_key_hex = "bb" * 32

        # Build header without content hash (clients don't send hash when server
        # uses accept_untrusted_content=True)
        auth_header = build_hawk_header(
            token_id_hex,
            bytes.fromhex(req_hmac_key_hex),
            "POST",
            "/v1/oauth/token",
            "localhost",
            "443",
        )

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"SESSION#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "verified": {"BOOL": True},
                    "expiry": {"N": "1002592000"},
                    "reqHMACkey": {"S": req_hmac_key_hex},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"SESSION#{token_id_hex}"},
            },
        )

        # Nonce replay protection: put_item for nonce record
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": ANY,
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        result = manager.verify_session_hawk(
            auth_header, "POST", "/v1/oauth/token", "localhost", "443"
        )

        assert result == sample_uid

    def test_returns_uid_when_client_sends_content_hash(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_session_hawk returns uid even when client includes content hash"""
        token_id_hex = "aa" * 32
        req_hmac_key_hex = "bb" * 32

        # Build header WITH content hash (Firefox includes this for POST)
        auth_header = build_hawk_header(
            token_id_hex,
            bytes.fromhex(req_hmac_key_hex),
            "POST",
            "/v1/oauth/token",
            "localhost",
            "443",
            content='{"grant_type":"fxa-credentials"}',
            content_type="application/json",
        )

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"SESSION#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "verified": {"BOOL": True},
                    "expiry": {"N": "1002592000"},
                    "reqHMACkey": {"S": req_hmac_key_hex},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"SESSION#{token_id_hex}"},
            },
        )

        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": ANY,
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        result = manager.verify_session_hawk(
            auth_header, "POST", "/v1/oauth/token", "localhost", "443"
        )

        assert result == sample_uid

    def test_returns_none_for_malformed_hawk_header(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_session_hawk returns None for completely malformed header"""
        # Not a valid Hawk header at all
        auth_header = "Bearer some-token"

        result = manager.verify_session_hawk(
            auth_header, "GET", "/v1/session/status", "localhost", "443"
        )

        assert result is None

    def test_returns_none_for_replayed_nonce(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_session_hawk returns None when nonce has been replayed"""
        token_id_hex = "aa" * 32
        req_hmac_key_hex = "bb" * 32

        auth_header = build_hawk_header(
            token_id_hex,
            bytes.fromhex(req_hmac_key_hex),
            "GET",
            "/v1/session/status",
            "localhost",
            "443",
        )

        # Stub: credential lookup succeeds
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"SESSION#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "verified": {"BOOL": True},
                    "expiry": {"N": "1002592000"},
                    "reqHMACkey": {"S": req_hmac_key_hex},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"SESSION#{token_id_hex}"},
            },
        )

        # Stub: nonce already seen
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="The conditional request failed",
        )

        result = manager.verify_session_hawk(
            auth_header, "GET", "/v1/session/status", "localhost", "443"
        )
        assert result is None

    def test_reraises_non_conditional_nonce_error(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_session_hawk re-raises non-ConditionalCheckFailed errors from nonce check"""
        from botocore.exceptions import ClientError

        token_id_hex = "aa" * 32
        req_hmac_key_hex = "bb" * 32

        auth_header = build_hawk_header(
            token_id_hex,
            bytes.fromhex(req_hmac_key_hex),
            "GET",
            "/v1/session/status",
            "localhost",
            "443",
        )

        # Stub: credential lookup succeeds
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"SESSION#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "verified": {"BOOL": True},
                    "expiry": {"N": "1002592000"},
                    "reqHMACkey": {"S": req_hmac_key_hex},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"SESSION#{token_id_hex}"},
            },
        )

        # Stub: nonce check fails with non-conditional error
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="InternalServerError",
            service_message="Internal server error",
        )

        with pytest.raises(ClientError) as exc_info:
            manager.verify_session_hawk(
                auth_header, "GET", "/v1/session/status", "localhost", "443"
            )
        assert exc_info.value.response["Error"]["Code"] == "InternalServerError"


class TestVerifyKeyfetchHawk:
    """Tests for verify_keyfetch_hawk method"""

    @pytest.fixture
    def manager(self, dynamodb_table):
        return FxATokenManager(table=dynamodb_table)

    @pytest.fixture
    def sample_uid(self):
        return "abcdef1234567890abcdef1234567890"

    @pytest.fixture
    def mock_time(self):
        with patch("src.services.fxa_token_manager.time") as mock:
            mock.time.return_value = 1000000.0
            yield mock

    def test_returns_token_data_for_valid_hawk(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_keyfetch_hawk returns uid and keyFetchToken when HMAC is valid"""
        token_id_hex = "aa" * 32
        req_hmac_key_hex = "bb" * 32
        raw_token_hex = "cc" * 32

        auth_header = build_hawk_header(
            token_id_hex,
            bytes.fromhex(req_hmac_key_hex),
            "GET",
            "/v1/account/keys",
            "localhost",
            "443",
        )

        dynamodb_stubber.add_response(
            "delete_item",
            {
                "Attributes": {
                    "PK": {"S": f"KEYFETCH#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "keyFetchToken": {"S": raw_token_hex},
                    "reqHMACkey": {"S": req_hmac_key_hex},
                    "expiry": {"N": "1000300"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"KEYFETCH#{token_id_hex}"},
                "ReturnValues": "ALL_OLD",
                "ConditionExpression": "attribute_exists(PK)",
            },
        )

        # Nonce replay protection: put_item for nonce record
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": ANY,
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        result = manager.verify_keyfetch_hawk(
            auth_header, "GET", "/v1/account/keys", "localhost", "443"
        )

        assert result is not None
        assert result["uid"] == sample_uid
        assert result["keyFetchToken"] == raw_token_hex

    def test_returns_none_for_unknown_token(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """verify_keyfetch_hawk returns None when token doesn't exist"""
        token_id_hex = "aa" * 32
        auth_header = f'Hawk id="{token_id_hex}", ts="1000000", nonce="abc", mac="AAAA"'

        dynamodb_stubber.add_client_error(
            "delete_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="The conditional request failed",
        )

        result = manager.verify_keyfetch_hawk(
            auth_header, "GET", "/v1/account/keys", "localhost", "443"
        )

        assert result is None

    def test_returns_none_for_missing_header(self, manager):
        """verify_keyfetch_hawk returns None when header is empty"""
        result = manager.verify_keyfetch_hawk("", "GET", "/path", "host", "443")
        assert result is None

    def test_returns_none_for_expired_keyfetch(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_keyfetch_hawk returns None when token is expired"""
        token_id_hex = "aa" * 32
        req_hmac_key_hex = "bb" * 32

        auth_header = build_hawk_header(
            token_id_hex,
            bytes.fromhex(req_hmac_key_hex),
            "GET",
            "/v1/account/keys",
            "localhost",
            "443",
        )

        dynamodb_stubber.add_response(
            "delete_item",
            {
                "Attributes": {
                    "PK": {"S": f"KEYFETCH#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "keyFetchToken": {"S": "cc" * 32},
                    "reqHMACkey": {"S": req_hmac_key_hex},
                    "expiry": {"N": "999999"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"KEYFETCH#{token_id_hex}"},
                "ReturnValues": "ALL_OLD",
                "ConditionExpression": "attribute_exists(PK)",
            },
        )

        result = manager.verify_keyfetch_hawk(
            auth_header, "GET", "/v1/account/keys", "localhost", "443"
        )
        assert result is None

    def test_returns_none_for_invalid_mac(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_keyfetch_hawk returns None when HMAC does not match"""
        token_id_hex = "aa" * 32
        req_hmac_key_hex = "bb" * 32

        auth_header = f'Hawk id="{token_id_hex}", ts="1000000", nonce="abc", mac="AAAA"'

        dynamodb_stubber.add_response(
            "delete_item",
            {
                "Attributes": {
                    "PK": {"S": f"KEYFETCH#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "keyFetchToken": {"S": "cc" * 32},
                    "reqHMACkey": {"S": req_hmac_key_hex},
                    "expiry": {"N": "1000300"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"KEYFETCH#{token_id_hex}"},
                "ReturnValues": "ALL_OLD",
                "ConditionExpression": "attribute_exists(PK)",
            },
        )

        result = manager.verify_keyfetch_hawk(
            auth_header, "GET", "/v1/account/keys", "localhost", "443"
        )
        assert result is None

    def test_returns_none_for_missing_hmac_key(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_keyfetch_hawk returns None when reqHMACkey is absent"""
        token_id_hex = "aa" * 32
        auth_header = f'Hawk id="{token_id_hex}", ts="1000000", nonce="abc", mac="AAAA"'

        dynamodb_stubber.add_response(
            "delete_item",
            {
                "Attributes": {
                    "PK": {"S": f"KEYFETCH#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "keyFetchToken": {"S": "cc" * 32},
                    "expiry": {"N": "1000300"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"KEYFETCH#{token_id_hex}"},
                "ReturnValues": "ALL_OLD",
                "ConditionExpression": "attribute_exists(PK)",
            },
        )

        result = manager.verify_keyfetch_hawk(
            auth_header, "GET", "/v1/account/keys", "localhost", "443"
        )
        assert result is None

    def test_reraises_non_conditional_error(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """verify_keyfetch_hawk re-raises non-ConditionalCheckFailed errors"""
        from botocore.exceptions import ClientError

        token_id_hex = "aa" * 32
        auth_header = f'Hawk id="{token_id_hex}", ts="1000000", nonce="abc", mac="AAAA"'

        dynamodb_stubber.add_client_error(
            "delete_item",
            service_error_code="InternalServerError",
            service_message="Internal server error",
        )

        with pytest.raises(ClientError) as exc_info:
            manager.verify_keyfetch_hawk(auth_header, "GET", "/v1/account/keys", "localhost", "443")
        assert exc_info.value.response["Error"]["Code"] == "InternalServerError"

    def test_returns_none_for_empty_attributes(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        mock_time,
    ):
        """verify_keyfetch_hawk returns None when Attributes is empty"""
        token_id_hex = "aa" * 32
        auth_header = f'Hawk id="{token_id_hex}", ts="1000000", nonce="abc", mac="AAAA"'

        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"KEYFETCH#{token_id_hex}"},
                "ReturnValues": "ALL_OLD",
                "ConditionExpression": "attribute_exists(PK)",
            },
        )

        result = manager.verify_keyfetch_hawk(
            auth_header, "GET", "/v1/account/keys", "localhost", "443"
        )
        assert result is None

    def test_returns_token_data_for_post_request(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_keyfetch_hawk returns uid and keyFetchToken for POST requests"""
        token_id_hex = "aa" * 32
        req_hmac_key_hex = "bb" * 32
        raw_token_hex = "cc" * 32

        # Build header without content hash
        auth_header = build_hawk_header(
            token_id_hex,
            bytes.fromhex(req_hmac_key_hex),
            "POST",
            "/v1/account/keys",
            "localhost",
            "443",
        )

        dynamodb_stubber.add_response(
            "delete_item",
            {
                "Attributes": {
                    "PK": {"S": f"KEYFETCH#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "keyFetchToken": {"S": raw_token_hex},
                    "reqHMACkey": {"S": req_hmac_key_hex},
                    "expiry": {"N": "1000300"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"KEYFETCH#{token_id_hex}"},
                "ReturnValues": "ALL_OLD",
                "ConditionExpression": "attribute_exists(PK)",
            },
        )

        # Nonce replay protection: put_item for nonce record
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": ANY,
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        result = manager.verify_keyfetch_hawk(
            auth_header, "POST", "/v1/account/keys", "localhost", "443"
        )

        assert result is not None
        assert result["uid"] == sample_uid
        assert result["keyFetchToken"] == raw_token_hex

    def test_returns_none_for_replayed_nonce(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        mock_time,
    ):
        """verify_keyfetch_hawk returns None when nonce has been replayed"""
        token_id_hex = "aa" * 32
        req_hmac_key_hex = "bb" * 32
        raw_token_hex = "cc" * 32

        auth_header = build_hawk_header(
            token_id_hex,
            bytes.fromhex(req_hmac_key_hex),
            "GET",
            "/v1/account/keys",
            "localhost",
            "443",
        )

        # Stub: credential lookup succeeds (atomic delete)
        dynamodb_stubber.add_response(
            "delete_item",
            {
                "Attributes": {
                    "PK": {"S": f"KEYFETCH#{token_id_hex}"},
                    "uid": {"S": sample_uid},
                    "keyFetchToken": {"S": raw_token_hex},
                    "reqHMACkey": {"S": req_hmac_key_hex},
                    "expiry": {"N": "1000300"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"KEYFETCH#{token_id_hex}"},
                "ReturnValues": "ALL_OLD",
                "ConditionExpression": "attribute_exists(PK)",
            },
        )

        # Stub: nonce already seen
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="The conditional request failed",
        )

        result = manager.verify_keyfetch_hawk(
            auth_header, "GET", "/v1/account/keys", "localhost", "443"
        )
        assert result is None


class TestVerifyKeyfetchHawkEdgeCases:
    """Edge case tests for verify_keyfetch_hawk"""

    @pytest.fixture
    def manager(self, dynamodb_table):
        return FxATokenManager(table=dynamodb_table)

    def test_returns_none_when_receiver_skips_credentials_map(self, manager):
        """verify_keyfetch_hawk returns None when result_holder has no uid
        (edge case: mohawk.Receiver completes but credentials_map was not invoked)"""
        token_id_hex = "aa" * 32
        auth_header = f'Hawk id="{token_id_hex}", ts="1000000", nonce="abc", mac="AAAA"'

        with patch("src.services.fxa_token_manager.mohawk.Receiver"):
            # Mock Receiver to succeed without calling credentials_map,
            # so result_holder stays empty
            result = manager.verify_keyfetch_hawk(
                auth_header, "GET", "/v1/account/keys", "localhost", "443"
            )
        assert result is None


class TestDeleteSession:
    """Tests for delete_session method"""

    @pytest.fixture
    def manager(self, dynamodb_table):
        return FxATokenManager(table=dynamodb_table)

    def test_deletes_session_record(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """delete_session deletes the SESSION# record"""
        token_id_hex = "ff" * 32

        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"SESSION#{token_id_hex}"},
            },
        )

        manager.delete_session(token_id_hex)

        dynamodb_stubber.assert_no_pending_responses()


class TestConstants:
    """Tests for module-level constants"""

    def test_session_token_info(self):
        assert SESSION_TOKEN_INFO == "identity.mozilla.com/picl/v1/sessionToken"

    def test_key_fetch_token_info(self):
        assert KEY_FETCH_TOKEN_INFO == "identity.mozilla.com/picl/v1/keyFetchToken"


class TestCustomTTL:
    """Tests for custom TTL values"""

    @pytest.fixture
    def fixed_token(self):
        return b"\xaa" * 32

    @pytest.fixture
    def mock_time(self):
        with patch("src.services.fxa_token_manager.time") as mock:
            mock.time.return_value = 1000000.0
            yield mock

    def test_custom_session_ttl(
        self,
        dynamodb_table,
        dynamodb_stubber,
        storage_table_name,
        fixed_token,
        mock_time,
    ):
        """Custom session_ttl_seconds is used for session token expiry"""
        custom_ttl = 3600  # 1 hour
        manager = FxATokenManager(table=dynamodb_table, session_ttl_seconds=custom_ttl)

        with patch("src.services.fxa_token_manager.fxa_crypto") as mock_crypto:
            mock_crypto.generate_random_bytes.return_value = fixed_token
            token_id = fxa_crypto.derive_token_id(fixed_token, SESSION_TOKEN_INFO)
            req_hmac_key = fxa_crypto.derive_req_hmac_key(fixed_token, SESSION_TOKEN_INFO)
            mock_crypto.derive_token_id.return_value = token_id
            mock_crypto.derive_req_hmac_key.return_value = req_hmac_key
            token_id_hex = token_id.hex()

            dynamodb_stubber.add_response(
                "put_item",
                {},
                {
                    "TableName": storage_table_name,
                    "Item": {
                        "PK": f"SESSION#{token_id_hex}",
                        "uid": "test-uid",
                        "verified": True,
                        "createdAt": 1000000000,
                        "expiry": 1000000 + custom_ttl,
                        "reqHMACkey": req_hmac_key.hex(),
                    },
                },
            )

            manager.create_session_token("test-uid")

        dynamodb_stubber.assert_no_pending_responses()

    def test_custom_keyfetch_ttl(
        self,
        dynamodb_table,
        dynamodb_stubber,
        storage_table_name,
        fixed_token,
        mock_time,
    ):
        """Custom keyfetch_ttl_seconds is used for key-fetch token expiry"""
        custom_ttl = 60  # 1 minute
        manager = FxATokenManager(table=dynamodb_table, keyfetch_ttl_seconds=custom_ttl)

        with patch("src.services.fxa_token_manager.fxa_crypto") as mock_crypto:
            mock_crypto.generate_random_bytes.return_value = fixed_token
            token_id = fxa_crypto.derive_token_id(fixed_token, KEY_FETCH_TOKEN_INFO)
            req_hmac_key = fxa_crypto.derive_req_hmac_key(fixed_token, KEY_FETCH_TOKEN_INFO)
            mock_crypto.derive_token_id.return_value = token_id
            mock_crypto.derive_req_hmac_key.return_value = req_hmac_key
            token_id_hex = token_id.hex()

            dynamodb_stubber.add_response(
                "put_item",
                {},
                {
                    "TableName": storage_table_name,
                    "Item": {
                        "PK": f"KEYFETCH#{token_id_hex}",
                        "uid": "test-uid",
                        "keyFetchToken": fixed_token.hex(),
                        "reqHMACkey": req_hmac_key.hex(),
                        "expiry": 1000000 + custom_ttl,
                    },
                },
            )

            manager.create_key_fetch_token("test-uid")

        dynamodb_stubber.assert_no_pending_responses()
