"""Tests for model classes and utility functions"""

from datetime import datetime
from unittest.mock import patch

import pytest

from src.shared.models import (
    BasicStorageObject,
    BatchResult,
    CollectionData,
    ValidationError,
    get_current_timestamp,
    validate_timestamp,
)


class TestBasicStorageObject:
    """Tests for BasicStorageObject model"""

    def test_creation_with_all_fields(self):
        """Test creating BSO with all fields"""
        bso = BasicStorageObject(
            id="test_id",
            payload="test_payload",
            modified=1234567890.12,
            sortindex=100,
            ttl=3600,
        )

        assert bso.id == "test_id"
        assert bso.payload == "test_payload"
        assert bso.modified == 1234567890.12
        assert bso.sortindex == 100
        assert bso.ttl == 3600

    def test_creation_with_optional_fields_none(self):
        """Test creating BSO with optional fields as None"""
        bso = BasicStorageObject(
            id="test_id",
            payload="test_payload",
            modified=1234567890.12,
            sortindex=None,
            ttl=None,
        )

        assert bso.id == "test_id"
        assert bso.payload == "test_payload"
        assert bso.modified == 1234567890.12
        assert bso.sortindex is None
        assert bso.ttl is None

    def test_creation_without_optional_fields(self):
        """Test creating BSO without specifying optional fields"""
        bso = BasicStorageObject(id="test_id", payload="test_payload", modified=1234567890.12)

        assert bso.id == "test_id"
        assert bso.sortindex is None
        assert bso.ttl is None

    def test_to_dict(self):
        """Test converting BSO to dictionary"""
        bso = BasicStorageObject(
            id="test_id",
            payload="test_payload",
            modified=1234567890.12,
            sortindex=50,
            ttl=7200,
        )

        bso_dict = bso.to_dict()

        assert bso_dict["id"] == "test_id"
        assert bso_dict["payload"] == "test_payload"
        assert bso_dict["modified"] == 1234567890.12
        assert bso_dict["sortindex"] == 50
        assert bso_dict["ttl"] == 7200

    def test_from_dict(self):
        """Test creating BSO from dictionary"""
        data = {
            "id": "test_id",
            "payload": "test_payload",
            "modified": 1234567890.12,
            "sortindex": 75,
            "ttl": 1800,
        }

        bso = BasicStorageObject.from_dict(data)

        assert bso.id == "test_id"
        assert bso.payload == "test_payload"
        assert bso.sortindex == 75
        assert bso.ttl == 1800


class TestCollectionData:
    """Tests for CollectionData model"""

    def test_creation(self):
        """Test creating collection data"""
        collection = CollectionData(name="bookmarks", modified=1234567890.12, count=10, usage=2048)

        assert collection.name == "bookmarks"
        assert collection.modified == 1234567890.12
        assert collection.count == 10
        assert collection.usage == 2048

    def test_to_dict(self):
        """Test converting collection to dictionary"""
        collection = CollectionData(name="history", modified=1234567880.00, count=100, usage=10240)

        collection_dict = collection.to_dict()

        assert collection_dict["name"] == "history"
        assert collection_dict["modified"] == 1234567880.00
        assert collection_dict["count"] == 100
        assert collection_dict["usage"] == 10240

    def test_from_dict(self):
        """Test creating collection from dictionary"""
        data = {"name": "tabs", "modified": 1234567870.00, "count": 5, "usage": 512}

        collection = CollectionData.from_dict(data)

        assert collection.name == "tabs"
        assert collection.modified == 1234567870.00
        assert collection.count == 5
        assert collection.usage == 512


class TestBatchResult:
    """Tests for BatchResult model"""

    def test_creation_all_success(self):
        """Test creating batch result with all successes"""
        result = BatchResult(success=["obj1", "obj2", "obj3"], failed={}, modified=1234567890.12)

        assert result.success == ["obj1", "obj2", "obj3"]
        assert result.failed == {}
        assert result.modified == 1234567890.12

    def test_creation_with_failures(self):
        """Test creating batch result with failures"""
        result = BatchResult(
            success=["obj1", "obj2"],
            failed={"obj3": ["validation error"], "obj4": ["missing field"]},
            modified=1234567890.12,
        )

        assert result.success == ["obj1", "obj2"]
        assert result.failed == {
            "obj3": ["validation error"],
            "obj4": ["missing field"],
        }
        assert result.modified == 1234567890.12

    def test_creation_all_failed(self):
        """Test creating batch result with all failures"""
        result = BatchResult(
            success=[],
            failed={"obj1": ["error1"], "obj2": ["error2"]},
            modified=1234567890.12,
        )

        assert result.success == []
        assert len(result.failed) == 2

    def test_to_dict(self):
        """Test converting batch result to dictionary"""
        result = BatchResult(success=["obj1"], failed={"obj2": ["error"]}, modified=1234567890.12)

        result_dict = result.to_dict()

        assert result_dict["success"] == ["obj1"]
        assert result_dict["failed"] == {"obj2": ["error"]}
        assert result_dict["modified"] == 1234567890.12

    def test_from_dict(self):
        """Test creating batch result from dictionary"""
        data = {
            "success": ["obj1", "obj2"],
            "failed": {"obj3": ["validation error"]},
            "modified": 1234567890.12,
        }

        result = BatchResult.from_dict(data)

        assert result.success == ["obj1", "obj2"]
        assert result.failed == {"obj3": ["validation error"]}


class TestValidationError:
    """Tests for ValidationError exception"""

    def test_creation(self):
        """Test creating ValidationError"""
        error = ValidationError("Invalid input")

        assert str(error) == "Invalid input"
        assert isinstance(error, Exception)

    def test_raise_and_catch(self):
        """Test raising and catching ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError("Test validation error")

        assert str(exc_info.value) == "Test validation error"


class TestGetCurrentTimestamp:
    """Tests for get_current_timestamp function"""

    def test_returns_float(self):
        """Test that function returns a float"""
        timestamp = get_current_timestamp()

        assert isinstance(timestamp, float)

    def test_returns_positive_value(self):
        """Test that timestamp is positive"""
        timestamp = get_current_timestamp()

        assert timestamp > 0

    def test_returns_reasonable_value(self):
        """Test that timestamp is in reasonable range (after 2020, before 2100)"""
        timestamp = get_current_timestamp()

        # Timestamp for 2020-01-01
        min_timestamp = 1577836800.0
        # Timestamp for 2100-01-01
        max_timestamp = 4102444800.0

        assert min_timestamp < timestamp < max_timestamp

    def test_has_two_decimal_places(self):
        """Test that timestamp has at most 2 decimal places"""
        timestamp = get_current_timestamp()

        # Round to 2 decimal places and compare
        rounded = round(timestamp, 2)
        assert abs(timestamp - rounded) < 1e-10

    def test_mocked_timestamp(self):
        """Test with mocked datetime"""
        mock_datetime = datetime(2024, 1, 1, 12, 0, 0)
        expected_timestamp = mock_datetime.timestamp()

        with patch("src.shared.models.datetime") as mock_dt:
            mock_dt.now.return_value = mock_datetime
            timestamp = get_current_timestamp()

            assert round(timestamp, 2) == round(expected_timestamp, 2)

    def test_consecutive_calls_increase(self):
        """Test that consecutive calls return increasing values"""
        timestamp1 = get_current_timestamp()
        timestamp2 = get_current_timestamp()

        assert timestamp2 >= timestamp1


class TestValidateTimestamp:
    """Tests for validate_timestamp function"""

    def test_valid_integer_timestamp(self):
        """Test validation of integer timestamps"""
        assert validate_timestamp(1234567890) is True
        assert validate_timestamp(0) is True
        assert validate_timestamp(9999999999) is True

    def test_valid_float_timestamp_two_decimals(self):
        """Test validation of float with 2 decimal places"""
        assert validate_timestamp(1234567890.12) is True
        assert validate_timestamp(1234567890.00) is True
        assert validate_timestamp(1234567890.99) is True

    def test_valid_float_timestamp_one_decimal(self):
        """Test validation of float with 1 decimal place"""
        assert validate_timestamp(1234567890.1) is True
        assert validate_timestamp(1234567890.5) is True

    def test_valid_float_timestamp_no_decimals(self):
        """Test validation of float with no decimal places"""
        assert validate_timestamp(1234567890.0) is True

    def test_invalid_too_many_decimals(self):
        """Test rejection of timestamps with too many decimal places"""
        assert validate_timestamp(1234567890.123) is False
        assert validate_timestamp(1234567890.1234) is False
        assert validate_timestamp(1234567890.12345) is False

    def test_invalid_negative_timestamp(self):
        """Test rejection of negative timestamps"""
        assert validate_timestamp(-1) is False
        assert validate_timestamp(-1234567890.12) is False
        assert validate_timestamp(-0.01) is False

    def test_invalid_non_numeric_types(self):
        """Test rejection of non-numeric types"""
        assert validate_timestamp("1234567890") is False
        assert validate_timestamp("1234567890.12") is False
        assert validate_timestamp(None) is False
        assert validate_timestamp([]) is False
        assert validate_timestamp({}) is False

    def test_edge_case_zero(self):
        """Test edge case of zero timestamp"""
        assert validate_timestamp(0) is True
        assert validate_timestamp(0.0) is True
        assert validate_timestamp(0.00) is True

    def test_edge_case_very_large(self):
        """Test edge case of very large timestamp"""
        assert validate_timestamp(9999999999.99) is True

    def test_precision_boundary(self):
        """Test precision boundary cases"""
        # Exactly 2 decimal places - valid
        assert validate_timestamp(1234567890.12) is True

        # More than 2 decimal places - invalid
        assert validate_timestamp(1234567890.125) is False

        # Less than 2 decimal places - valid
        assert validate_timestamp(1234567890.1) is True
