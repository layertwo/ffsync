import pytest

from src.shared.models import (
    MAX_BSO_ID_LENGTH,
    MAX_COLLECTION_NAME_LENGTH,
    MAX_PAYLOAD_BYTES,
    MAX_SORTINDEX,
    MAX_TTL,
    MIN_SORTINDEX,
    ValidationError,
    validate_bso_id,
    validate_collection_name,
    validate_payload_size,
    validate_sortindex,
    validate_ttl,
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


class TestValidateSortindex:
    def test_valid_sortindex(self):
        """Valid sortindex should not raise exception"""
        validate_sortindex(100)  # Should not raise

    def test_none_sortindex(self):
        """None sortindex should be valid"""
        validate_sortindex(None)  # Should not raise

    def test_sortindex_at_max(self):
        """Sortindex at max value should be valid"""
        validate_sortindex(MAX_SORTINDEX)  # Should not raise

    def test_sortindex_at_min(self):
        """Sortindex at min value should be valid"""
        validate_sortindex(MIN_SORTINDEX)  # Should not raise

    def test_sortindex_exceeds_max(self):
        """Sortindex exceeding max should raise ValidationError"""
        with pytest.raises(ValidationError, match="exceeds maximum 9 digits"):
            validate_sortindex(MAX_SORTINDEX + 1)

    def test_sortindex_below_min(self):
        """Sortindex below min should raise ValidationError"""
        with pytest.raises(ValidationError, match="exceeds maximum 9 digits"):
            validate_sortindex(MIN_SORTINDEX - 1)

    def test_sortindex_not_integer(self):
        """Non-integer sortindex should raise ValidationError"""
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_sortindex("100")  # type: ignore


class TestValidateTTL:
    def test_valid_ttl(self):
        """Valid TTL should not raise exception"""
        validate_ttl(3600)  # Should not raise

    def test_none_ttl(self):
        """None TTL should be valid"""
        validate_ttl(None)  # Should not raise

    def test_ttl_at_max(self):
        """TTL at max value should be valid"""
        validate_ttl(MAX_TTL)  # Should not raise

    def test_ttl_exceeds_max(self):
        """TTL exceeding max should raise ValidationError"""
        with pytest.raises(ValidationError, match="exceeds maximum 9 digits"):
            validate_ttl(MAX_TTL + 1)

    def test_ttl_zero(self):
        """TTL of zero should raise ValidationError"""
        with pytest.raises(ValidationError, match="must be a positive integer"):
            validate_ttl(0)

    def test_ttl_negative(self):
        """Negative TTL should raise ValidationError"""
        with pytest.raises(ValidationError, match="must be a positive integer"):
            validate_ttl(-100)

    def test_ttl_not_integer(self):
        """Non-integer TTL should raise ValidationError"""
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_ttl("3600")  # type: ignore


class TestValidateBSOId:
    def test_valid_bso_id(self):
        """Valid BSO ID should not raise exception"""
        validate_bso_id("valid-bso-id-123")  # Should not raise

    def test_bso_id_at_max_length(self):
        """BSO ID at max length should be valid"""
        bso_id = "a" * MAX_BSO_ID_LENGTH
        validate_bso_id(bso_id)  # Should not raise

    def test_bso_id_exceeds_max_length(self):
        """BSO ID exceeding max length should raise ValidationError"""
        bso_id = "a" * (MAX_BSO_ID_LENGTH + 1)
        with pytest.raises(ValidationError, match="exceeds maximum .* characters"):
            validate_bso_id(bso_id)

    def test_bso_id_with_non_printable_ascii(self):
        """BSO ID with non-printable ASCII should raise ValidationError"""
        bso_id = "test\x00id"  # Contains null character
        with pytest.raises(ValidationError, match="non-printable ASCII character"):
            validate_bso_id(bso_id)

    def test_bso_id_with_tab(self):
        """BSO ID with tab character should raise ValidationError"""
        bso_id = "test\tid"
        with pytest.raises(ValidationError, match="non-printable ASCII character"):
            validate_bso_id(bso_id)

    def test_bso_id_with_newline(self):
        """BSO ID with newline should raise ValidationError"""
        bso_id = "test\nid"
        with pytest.raises(ValidationError, match="non-printable ASCII character"):
            validate_bso_id(bso_id)

    def test_bso_id_with_all_printable_ascii(self):
        """BSO ID with all printable ASCII characters should be valid"""
        # Printable ASCII: 0x20 (space) to 0x7E (~)
        bso_id = "abc123 !@#$%^&*()_+-=[]{}|;:',.<>?/~"
        validate_bso_id(bso_id)  # Should not raise


class TestValidateCollectionName:
    def test_valid_collection_name(self):
        """Valid collection name should not raise exception"""
        validate_collection_name("bookmarks")  # Should not raise

    def test_collection_name_with_underscore(self):
        """Collection name with underscore should be valid"""
        validate_collection_name("my_collection")  # Should not raise

    def test_collection_name_with_hyphen(self):
        """Collection name with hyphen should be valid"""
        validate_collection_name("my-collection")  # Should not raise

    def test_collection_name_with_period(self):
        """Collection name with period should be valid"""
        validate_collection_name("my.collection")  # Should not raise

    def test_collection_name_with_mixed_chars(self):
        """Collection name with mixed valid characters should be valid"""
        validate_collection_name("My_Collection-123.test")  # Should not raise

    def test_collection_name_at_max_length(self):
        """Collection name at max length should be valid"""
        name = "a" * MAX_COLLECTION_NAME_LENGTH
        validate_collection_name(name)  # Should not raise

    def test_collection_name_exceeds_max_length(self):
        """Collection name exceeding max length should raise ValidationError"""
        name = "a" * (MAX_COLLECTION_NAME_LENGTH + 1)
        with pytest.raises(ValidationError, match="exceeds maximum .* characters"):
            validate_collection_name(name)

    def test_collection_name_with_space(self):
        """Collection name with space should raise ValidationError"""
        with pytest.raises(ValidationError, match="invalid character"):
            validate_collection_name("my collection")

    def test_collection_name_with_special_char(self):
        """Collection name with special character should raise ValidationError"""
        with pytest.raises(ValidationError, match="invalid character"):
            validate_collection_name("my@collection")

    def test_collection_name_with_slash(self):
        """Collection name with slash should raise ValidationError"""
        with pytest.raises(ValidationError, match="invalid character"):
            validate_collection_name("my/collection")
