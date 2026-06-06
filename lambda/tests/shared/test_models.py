from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.shared.models import (
    MAX_BSO_ID_LENGTH,
    MAX_COLLECTION_NAME_LENGTH,
    MAX_PAYLOAD_BYTES,
    AccountCreateInput,
    BatchResultOutput,
    BSOInput,
    CollectionDataOutput,
    DeviceOutput,
    ModifiedOutput,
    ValidationError,
    validate_bso_id,
    validate_collection_name,
    validate_payload_size,
)


class TestValidatePayloadSize:
    def test_valid_payload(self):
        """Valid payload should not raise exception"""
        payload = "a" * 1000
        validate_payload_size(payload)  # Should not raise

    def test_payload_at_max_size(self):
        """Payload at exactly max size should be valid"""
        payload = "a" * MAX_PAYLOAD_BYTES
        validate_payload_size(payload)  # Should not raise

    def test_payload_exceeds_max_size(self):
        """Payload exceeding max size should raise ValidationError"""
        payload = "a" * (MAX_PAYLOAD_BYTES + 1)
        with pytest.raises(ValidationError, match="Payload size .* exceeds maximum"):
            validate_payload_size(payload)

    def test_empty_payload(self):
        """Empty payload should be valid"""
        validate_payload_size("")  # Should not raise


class TestValidateBSOId:
    def test_valid_bso_id(self):
        """Valid BSO ID should not raise exception"""
        validate_bso_id("valid-bso-id")  # Should not raise

    def test_bso_id_at_max_length(self):
        """BSO ID at exactly max length should be valid"""
        validate_bso_id("a" * MAX_BSO_ID_LENGTH)  # Should not raise

    def test_bso_id_exceeds_max_length(self):
        """BSO ID exceeding max length should raise ValidationError"""
        with pytest.raises(ValidationError, match="BSO ID length .* exceeds maximum"):
            validate_bso_id("a" * (MAX_BSO_ID_LENGTH + 1))

    def test_bso_id_with_special_chars(self):
        """BSO ID with printable ASCII characters should be valid"""
        validate_bso_id("valid-bso-id_123.test")  # Should not raise

    def test_bso_id_with_non_printable_chars(self):
        """BSO ID with non-printable ASCII should raise ValidationError"""
        with pytest.raises(ValidationError, match="non-printable ASCII"):
            validate_bso_id("invalid\x00id")

    def test_bso_id_with_tab_char(self):
        """BSO ID with tab character should raise ValidationError"""
        with pytest.raises(ValidationError, match="non-printable ASCII"):
            validate_bso_id("invalid\tid")

    def test_bso_id_with_del_char(self):
        """BSO ID with DEL character (0x7F) should raise ValidationError"""
        with pytest.raises(ValidationError, match="non-printable ASCII"):
            validate_bso_id("invalid\x7fid")

    def test_empty_bso_id(self):
        """Empty BSO ID should be rejected (smithy ObjectId requires min length 1)"""
        with pytest.raises(ValidationError):
            validate_bso_id("")


class TestValidateCollectionName:
    def test_empty_collection_name(self):
        """Empty collection name should be rejected (smithy CollectionName min length 1)"""
        with pytest.raises(ValidationError):
            validate_collection_name("")

    def test_valid_collection_name(self):
        """Valid collection name should not raise exception"""
        validate_collection_name("bookmarks")  # Should not raise

    def test_collection_name_with_special_chars(self):
        """Collection name with allowed special characters"""
        validate_collection_name("my-collection_1.0")  # Should not raise

    def test_collection_name_with_invalid_chars(self):
        """Collection name with invalid characters should raise ValidationError"""
        with pytest.raises(ValidationError, match="invalid character"):
            validate_collection_name("invalid collection!")

    def test_collection_name_with_space(self):
        """Collection name with space should raise ValidationError"""
        with pytest.raises(ValidationError, match="invalid character"):
            validate_collection_name("invalid name")

    def test_collection_name_at_max_length(self):
        """Collection name at exactly max length should be valid"""
        validate_collection_name("a" * MAX_COLLECTION_NAME_LENGTH)  # Should not raise

    def test_collection_name_exceeds_max_length(self):
        """Collection name exceeding max length should raise ValidationError"""
        with pytest.raises(ValidationError, match="Collection name length .* exceeds maximum"):
            validate_collection_name("a" * (MAX_COLLECTION_NAME_LENGTH + 1))


class TestBSOInput:
    def test_all_fields_optional(self):
        bso = BSOInput()
        assert bso.id is None
        assert bso.payload is None
        assert bso.sortindex is None
        assert bso.ttl is None

    def test_sortindex_at_bounds(self):
        BSOInput(sortindex=999999999)
        BSOInput(sortindex=-999999999)

    def test_sortindex_out_of_range(self):
        with pytest.raises(PydanticValidationError):
            BSOInput(sortindex=1000000000)
        with pytest.raises(PydanticValidationError):
            BSOInput(sortindex=-1000000000)

    def test_ttl_must_be_positive(self):
        with pytest.raises(PydanticValidationError):
            BSOInput(ttl=0)
        with pytest.raises(PydanticValidationError):
            BSOInput(ttl=-1)

    def test_ttl_at_max(self):
        BSOInput(ttl=999999999)

    def test_ttl_exceeds_max(self):
        with pytest.raises(PydanticValidationError):
            BSOInput(ttl=1000000000)

    def test_payload_accepts_large_string(self):
        """Payload validation is byte-based (validate_payload_size), not char-based."""
        BSOInput(payload="a" * 262144)  # no Pydantic char limit


class TestCamelModelAliasing:
    def test_device_output_serializes_to_camel(self):
        dev = DeviceOutput(
            id="d1",
            name="My Phone",
            type="mobile",
            push_callback="https://push.example.com",
            created_at=1000,
            last_access_time=2000,
        )
        d = dev.model_dump(by_alias=True)
        assert "pushCallback" in d
        assert "pushPublicKey" in d
        assert "createdAt" in d
        assert "lastAccessTime" in d
        # snake_case keys should NOT appear when by_alias=True
        assert "push_callback" not in d

    def test_device_output_accepts_camel_input(self):
        dev = DeviceOutput.model_validate(
            {
                "id": "d1",
                "name": "Phone",
                "type": "mobile",
                "pushCallback": "https://push",
                "createdAt": 100,
                "lastAccessTime": 200,
            }
        )
        assert dev.push_callback == "https://push"
        assert dev.created_at == 100

    def test_device_output_accepts_snake_input(self):
        dev = DeviceOutput(
            id="d1",
            name="Phone",
            type="mobile",
            push_callback="https://push",
            created_at=100,
            last_access_time=200,
        )
        assert dev.push_callback == "https://push"


class TestBatchResultOutput:
    def test_basic_creation(self):
        br = BatchResultOutput(
            success=["a", "b"],
            failed={"c": ["error"]},
            modified=1.23,
        )
        assert br.model_dump() == {
            "success": ["a", "b"],
            "failed": {"c": ["error"]},
            "modified": 1.23,
        }


class TestCollectionDataOutput:
    def test_basic_creation(self):
        cd = CollectionDataOutput(name="bookmarks", modified=1.0, count=5, usage=1024)
        assert cd.name == "bookmarks"
        assert cd.count == 5


class TestModifiedOutput:
    def test_basic_creation(self):
        m = ModifiedOutput(modified=1.23)
        assert m.modified == 1.23


class TestAccountCreateInput:
    def test_valid(self):
        pw = "a" * 64
        a = AccountCreateInput(email="user@example.com", auth_pw=pw)
        assert a.auth_pw == pw

    def test_auth_pw_too_short(self):
        with pytest.raises(PydanticValidationError):
            AccountCreateInput(email="user@example.com", auth_pw="short")

    def test_auth_pw_too_long(self):
        with pytest.raises(PydanticValidationError):
            AccountCreateInput(email="user@example.com", auth_pw="a" * 65)


class TestToDynamoDict:
    def test_converts_float_to_decimal(self):
        from src.shared.models import BasicStorageObject, to_dynamo_dict

        bso = BasicStorageObject(id="x", payload="p", modified=3.14)
        dumped = to_dynamo_dict(bso)
        assert isinstance(dumped["modified"], Decimal)
        assert dumped["modified"] == Decimal("3.14")
        assert dumped["id"] == "x"
        assert dumped["payload"] == "p"

    def test_recurses_into_dict_and_list(self):
        from src.shared.models import _to_dynamo

        result = _to_dynamo({"a": 1.5, "b": [2.5, 3], "c": {"d": 4.0}})
        assert result == {
            "a": Decimal("1.5"),
            "b": [Decimal("2.5"), 3],
            "c": {"d": Decimal("4.0")},
        }


class TestDeviceOutputDecimalFields:
    def test_decimal_fields_convert_to_int(self):
        dev = DeviceOutput.model_validate(
            {
                "id": "d1",
                "name": "Phone",
                "type": "mobile",
                "created_at": Decimal("1000"),
                "last_access_time": Decimal("2000"),
            }
        )
        assert isinstance(dev.created_at, int)
        assert dev.created_at == 1000
        assert isinstance(dev.last_access_time, int)
        assert dev.last_access_time == 2000
