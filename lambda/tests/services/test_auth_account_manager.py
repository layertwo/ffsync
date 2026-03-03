"""Unit tests for AuthAccountManager with DynamoDB stubber"""

from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from src.services.auth_account_manager import AuthAccountManager


class TestAuthAccountManager:
    """Test AuthAccountManager DynamoDB operations"""

    @pytest.fixture
    def manager(self, dynamodb_table):
        """Create AuthAccountManager instance with stubbed table"""
        return AuthAccountManager(table=dynamodb_table)

    @pytest.fixture
    def sample_uid(self):
        return "abcdef1234567890abcdef1234567890"

    @pytest.fixture
    def sample_email(self):
        return "Test.User@Example.com"

    @pytest.fixture
    def sample_normalized_email(self):
        return "test.user@example.com"

    @pytest.fixture
    def sample_verify_hash(self):
        return "a" * 64

    @pytest.fixture
    def sample_k_a(self):
        return "b" * 64

    @pytest.fixture
    def sample_wrap_kb(self):
        return "c" * 64

    @pytest.fixture
    def sample_oidc_sub(self):
        return "oidc-sub-12345"

    @pytest.fixture
    def sample_key_rotation_secret(self):
        return "d" * 64

    @pytest.fixture
    def mock_time(self):
        """Mock time.time() for auth_account_manager"""
        with patch("src.services.auth_account_manager.time") as mock:
            mock.time.return_value = 1234567890.0
            yield mock

    # -- create_account -------------------------------------------------------

    def test_create_account_stores_email_then_account_records(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_email,
        sample_normalized_email,
        sample_verify_hash,
        sample_k_a,
        sample_wrap_kb,
        sample_oidc_sub,
        sample_key_rotation_secret,
        mock_time,
    ):
        """Test create_account stores EMAIL# first then ACCOUNT# record"""
        # Stub put_item for EMAIL# record first (with condition)
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"EMAIL#{sample_normalized_email}",
                    "uid": sample_uid,
                },
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        # Stub put_item for OIDCSUB# record
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"OIDCSUB#{sample_oidc_sub}",
                    "uid": sample_uid,
                },
            },
        )

        # Stub put_item for ACCOUNT# record
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"ACCOUNT#{sample_uid}",
                    "email": sample_normalized_email,
                    "uid": sample_uid,
                    "verifyHash": sample_verify_hash,
                    "kA": sample_k_a,
                    "wrapKB": sample_wrap_kb,
                    "oidcSub": sample_oidc_sub,
                    "keyRotationSecret": sample_key_rotation_secret,
                    "verified": True,
                    "createdAt": 1234567890000,
                },
            },
        )

        manager.create_account(
            uid=sample_uid,
            email=sample_email,
            verify_hash=sample_verify_hash,
            k_a=sample_k_a,
            wrap_kb=sample_wrap_kb,
            oidc_sub=sample_oidc_sub,
            key_rotation_secret=sample_key_rotation_secret,
        )

    def test_create_account_normalizes_email(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_verify_hash,
        sample_k_a,
        sample_wrap_kb,
        sample_oidc_sub,
        mock_time,
    ):
        """Test that email is lowercased and stripped during creation"""
        email = "  User@EXAMPLE.COM  "
        normalized = "user@example.com"

        # Stub put_item for EMAIL# record first
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"EMAIL#{normalized}",
                    "uid": sample_uid,
                },
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        # Stub put_item for OIDCSUB# record
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"OIDCSUB#{sample_oidc_sub}",
                    "uid": sample_uid,
                },
            },
        )

        # Stub put_item for ACCOUNT# record with normalized email
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"ACCOUNT#{sample_uid}",
                    "email": normalized,
                    "uid": sample_uid,
                    "verifyHash": sample_verify_hash,
                    "kA": sample_k_a,
                    "wrapKB": sample_wrap_kb,
                    "oidcSub": sample_oidc_sub,
                    "keyRotationSecret": "",
                    "verified": True,
                    "createdAt": 1234567890000,
                },
            },
        )

        manager.create_account(
            uid=sample_uid,
            email=email,
            verify_hash=sample_verify_hash,
            k_a=sample_k_a,
            wrap_kb=sample_wrap_kb,
            oidc_sub=sample_oidc_sub,
        )

    def test_create_account_rejects_duplicate_email(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_email,
        sample_normalized_email,
        sample_verify_hash,
        sample_k_a,
        sample_wrap_kb,
        sample_oidc_sub,
        mock_time,
    ):
        """Test that duplicate email raises ValueError"""
        # Stub EMAIL# put to fail with ConditionalCheckFailedException
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="The conditional request failed",
        )

        with pytest.raises(ValueError, match="already exists"):
            manager.create_account(
                uid=sample_uid,
                email=sample_email,
                verify_hash=sample_verify_hash,
                k_a=sample_k_a,
                wrap_kb=sample_wrap_kb,
                oidc_sub=sample_oidc_sub,
            )

    def test_create_account_cleans_up_email_on_oidcsub_write_failure(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_email,
        sample_normalized_email,
        sample_verify_hash,
        sample_k_a,
        sample_wrap_kb,
        sample_oidc_sub,
        mock_time,
    ):
        """If OIDCSUB# put fails, EMAIL# record is cleaned up"""
        # Stub successful EMAIL# put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"EMAIL#{sample_normalized_email}",
                    "uid": sample_uid,
                },
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        # Stub OIDCSUB# put to fail
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="InternalServerError",
            service_message="Internal server error",
        )

        # Stub delete_item for EMAIL# cleanup
        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"EMAIL#{sample_normalized_email}"},
            },
        )

        with pytest.raises(ClientError):
            manager.create_account(
                uid=sample_uid,
                email=sample_email,
                verify_hash=sample_verify_hash,
                k_a=sample_k_a,
                wrap_kb=sample_wrap_kb,
                oidc_sub=sample_oidc_sub,
            )

    def test_create_account_oidcsub_failure_with_email_cleanup_failure(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_email,
        sample_normalized_email,
        sample_verify_hash,
        sample_k_a,
        sample_wrap_kb,
        sample_oidc_sub,
        mock_time,
    ):
        """If OIDCSUB# put fails and EMAIL# cleanup also fails, original error is raised"""
        # Stub successful EMAIL# put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"EMAIL#{sample_normalized_email}",
                    "uid": sample_uid,
                },
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        # Stub OIDCSUB# put to fail
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="InternalServerError",
            service_message="Internal server error",
        )

        # Stub delete_item for EMAIL# cleanup to also fail
        dynamodb_stubber.add_client_error(
            "delete_item",
            service_error_code="InternalServerError",
            service_message="Cleanup also failed",
        )

        with pytest.raises(ClientError):
            manager.create_account(
                uid=sample_uid,
                email=sample_email,
                verify_hash=sample_verify_hash,
                k_a=sample_k_a,
                wrap_kb=sample_wrap_kb,
                oidc_sub=sample_oidc_sub,
            )

    # -- ensure_oidcsub_record ------------------------------------------------

    def test_ensure_oidcsub_record_creates_when_missing(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_oidc_sub,
    ):
        """Creates OIDCSUB# record when it doesn't exist"""
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"OIDCSUB#{sample_oidc_sub}",
                    "uid": sample_uid,
                },
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        manager.ensure_oidcsub_record(sample_uid, sample_oidc_sub)

    def test_ensure_oidcsub_record_noop_when_exists(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_oidc_sub,
    ):
        """No-op when OIDCSUB# record already exists"""
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="The conditional request failed",
        )

        manager.ensure_oidcsub_record(sample_uid, sample_oidc_sub)

    def test_ensure_oidcsub_record_raises_unexpected_error(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_oidc_sub,
    ):
        """Unexpected errors are re-raised"""
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="InternalServerError",
            service_message="Internal server error",
        )

        with pytest.raises(ClientError):
            manager.ensure_oidcsub_record(sample_uid, sample_oidc_sub)

    def test_ensure_oidcsub_record_noop_when_empty_sub(
        self,
        manager,
        sample_uid,
    ):
        """No-op when oidc_sub is empty"""
        manager.ensure_oidcsub_record(sample_uid, "")

    # -- get_account_by_oidc_sub ----------------------------------------------

    def test_get_account_by_oidc_sub_returns_account(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_normalized_email,
        sample_verify_hash,
        sample_k_a,
        sample_wrap_kb,
        sample_oidc_sub,
    ):
        """Test get_account_by_oidc_sub returns account for existing OIDC subject"""
        # Stub get_item for OIDCSUB# record
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"OIDCSUB#{sample_oidc_sub}"},
                    "uid": {"S": sample_uid},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"OIDCSUB#{sample_oidc_sub}"},
            },
        )

        # Stub get_item for ACCOUNT# record
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"ACCOUNT#{sample_uid}"},
                    "email": {"S": sample_normalized_email},
                    "uid": {"S": sample_uid},
                    "verifyHash": {"S": sample_verify_hash},
                    "kA": {"S": sample_k_a},
                    "wrapKB": {"S": sample_wrap_kb},
                    "oidcSub": {"S": sample_oidc_sub},
                    "verified": {"BOOL": True},
                    "createdAt": {"N": "1234567890000"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"ACCOUNT#{sample_uid}"},
            },
        )

        result = manager.get_account_by_oidc_sub(sample_oidc_sub)
        assert result is not None
        assert result["uid"] == sample_uid
        assert result["email"] == sample_normalized_email

    def test_get_account_by_oidc_sub_returns_none_for_unknown(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """Test get_account_by_oidc_sub returns None for unknown OIDC subject"""
        oidc_sub = "unknown-oidc-sub"

        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"OIDCSUB#{oidc_sub}"},
            },
        )

        result = manager.get_account_by_oidc_sub(oidc_sub)
        assert result is None

    # -- get_account_by_email -------------------------------------------------

    def test_get_account_by_email_returns_account(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_email,
        sample_normalized_email,
        sample_verify_hash,
        sample_k_a,
        sample_wrap_kb,
        sample_oidc_sub,
    ):
        """Test get_account_by_email returns account for existing email"""
        # Stub get_item for EMAIL# record
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"EMAIL#{sample_normalized_email}"},
                    "uid": {"S": sample_uid},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"EMAIL#{sample_normalized_email}"},
            },
        )

        # Stub get_item for ACCOUNT# record
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"ACCOUNT#{sample_uid}"},
                    "email": {"S": sample_normalized_email},
                    "uid": {"S": sample_uid},
                    "verifyHash": {"S": sample_verify_hash},
                    "kA": {"S": sample_k_a},
                    "wrapKB": {"S": sample_wrap_kb},
                    "oidcSub": {"S": sample_oidc_sub},
                    "verified": {"BOOL": True},
                    "createdAt": {"N": "1234567890000"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"ACCOUNT#{sample_uid}"},
            },
        )

        result = manager.get_account_by_email(sample_email)

        assert result is not None
        assert result["uid"] == sample_uid
        assert result["email"] == sample_normalized_email
        assert result["verifyHash"] == sample_verify_hash
        assert result["kA"] == sample_k_a
        assert result["wrapKB"] == sample_wrap_kb
        assert result["oidcSub"] == sample_oidc_sub
        assert result["verified"] is True
        assert result["createdAt"] == 1234567890000

    def test_get_account_by_email_returns_none_for_unknown(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """Test get_account_by_email returns None for unknown email"""
        email = "unknown@example.com"

        # Stub get_item for EMAIL# record returning empty
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"EMAIL#{email}"},
            },
        )

        result = manager.get_account_by_email(email)

        assert result is None

    # -- get_account_by_uid ---------------------------------------------------

    def test_get_account_by_uid_returns_account(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_normalized_email,
        sample_verify_hash,
        sample_k_a,
        sample_wrap_kb,
        sample_oidc_sub,
    ):
        """Test get_account_by_uid returns account for existing uid"""
        # Stub get_item for ACCOUNT# record
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"ACCOUNT#{sample_uid}"},
                    "email": {"S": sample_normalized_email},
                    "uid": {"S": sample_uid},
                    "verifyHash": {"S": sample_verify_hash},
                    "kA": {"S": sample_k_a},
                    "wrapKB": {"S": sample_wrap_kb},
                    "oidcSub": {"S": sample_oidc_sub},
                    "verified": {"BOOL": True},
                    "createdAt": {"N": "1234567890000"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"ACCOUNT#{sample_uid}"},
            },
        )

        result = manager.get_account_by_uid(sample_uid)

        assert result is not None
        assert result["uid"] == sample_uid
        assert result["email"] == sample_normalized_email
        assert result["verifyHash"] == sample_verify_hash
        assert result["kA"] == sample_k_a
        assert result["wrapKB"] == sample_wrap_kb
        assert result["oidcSub"] == sample_oidc_sub
        assert result["verified"] is True
        assert result["createdAt"] == 1234567890000

    def test_get_account_by_uid_returns_none_for_unknown(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """Test get_account_by_uid returns None for unknown uid"""
        uid = "nonexistent-uid-00000000000000000"

        # Stub get_item for ACCOUNT# record returning empty
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"ACCOUNT#{uid}"},
            },
        )

        result = manager.get_account_by_uid(uid)

        assert result is None

    def test_create_account_cleans_up_on_account_write_failure(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_email,
        sample_normalized_email,
        sample_verify_hash,
        sample_k_a,
        sample_wrap_kb,
        sample_oidc_sub,
        mock_time,
    ):
        """If ACCOUNT# put fails, EMAIL# and OIDCSUB# records are cleaned up"""
        # Stub successful EMAIL# put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"EMAIL#{sample_normalized_email}",
                    "uid": sample_uid,
                },
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        # Stub successful OIDCSUB# put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"OIDCSUB#{sample_oidc_sub}",
                    "uid": sample_uid,
                },
            },
        )

        # Stub ACCOUNT# put to fail
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="InternalServerError",
            service_message="Internal server error",
        )

        # Stub delete_item for EMAIL# cleanup
        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"EMAIL#{sample_normalized_email}"},
            },
        )

        # Stub delete_item for OIDCSUB# cleanup
        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"OIDCSUB#{sample_oidc_sub}"},
            },
        )

        with pytest.raises(ClientError):
            manager.create_account(
                uid=sample_uid,
                email=sample_email,
                verify_hash=sample_verify_hash,
                k_a=sample_k_a,
                wrap_kb=sample_wrap_kb,
                oidc_sub=sample_oidc_sub,
            )

    def test_create_account_cleans_up_even_if_cleanup_fails(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_email,
        sample_normalized_email,
        sample_verify_hash,
        sample_k_a,
        sample_wrap_kb,
        sample_oidc_sub,
        mock_time,
    ):
        """If ACCOUNT# put fails and cleanup also fails, the original error is raised"""
        # Stub successful EMAIL# put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"EMAIL#{sample_normalized_email}",
                    "uid": sample_uid,
                },
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        # Stub successful OIDCSUB# put
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"OIDCSUB#{sample_oidc_sub}",
                    "uid": sample_uid,
                },
            },
        )

        # Stub ACCOUNT# put to fail
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="InternalServerError",
            service_message="Internal server error",
        )

        # Stub delete_item for EMAIL# cleanup to also fail
        dynamodb_stubber.add_client_error(
            "delete_item",
            service_error_code="InternalServerError",
            service_message="Cleanup also failed",
        )

        # Stub delete_item for OIDCSUB# cleanup to also fail
        dynamodb_stubber.add_client_error(
            "delete_item",
            service_error_code="InternalServerError",
            service_message="Cleanup also failed",
        )

        with pytest.raises(ClientError):
            manager.create_account(
                uid=sample_uid,
                email=sample_email,
                verify_hash=sample_verify_hash,
                k_a=sample_k_a,
                wrap_kb=sample_wrap_kb,
                oidc_sub=sample_oidc_sub,
            )

    # -- create_account unexpected errors --------------------------------------

    def test_create_account_reraises_unexpected_client_error(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_email,
        sample_normalized_email,
        sample_verify_hash,
        sample_k_a,
        sample_wrap_kb,
        sample_oidc_sub,
        mock_time,
    ):
        """Test that unexpected ClientErrors on EMAIL# put are re-raised"""
        # Stub EMAIL# put to fail with unexpected error
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="InternalServerError",
            service_message="Internal server error",
        )

        with pytest.raises(ClientError) as exc_info:
            manager.create_account(
                uid=sample_uid,
                email=sample_email,
                verify_hash=sample_verify_hash,
                k_a=sample_k_a,
                wrap_kb=sample_wrap_kb,
                oidc_sub=sample_oidc_sub,
            )

        assert exc_info.value.response["Error"]["Code"] == "InternalServerError"
