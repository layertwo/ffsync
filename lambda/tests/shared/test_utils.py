"""Tests for shared utility functions"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.shared.utils import (
    DecimalEncoder,
    datetime_decoder,
    datetime_encoder,
    decimal_to_float,
    float_to_decimal,
    json_dumps,
)


class TestDatetimeEncoderDecoder:
    """Test datetime encoding and decoding"""

    def test_datetime_encoder_returns_decimal(self):
        """Test that datetime_encoder returns a Decimal"""
        dt = datetime(2009, 2, 13, 23, 31, 30, tzinfo=timezone.utc)
        result = datetime_encoder(dt)
        assert isinstance(result, Decimal)
        assert result == Decimal("1234567890.0")

    def test_datetime_decoder_returns_datetime(self):
        """Test that datetime_decoder returns a datetime"""
        timestamp = 1234567890.0
        result = datetime_decoder(timestamp)
        assert isinstance(result, datetime)
        assert result == datetime(2009, 2, 13, 23, 31, 30, tzinfo=timezone.utc)


class TestFloatDecimalConverters:
    """Test float to Decimal conversion utilities"""

    def test_float_to_decimal(self):
        """Test converting float to Decimal"""
        result = float_to_decimal(123.45)
        assert isinstance(result, Decimal)
        assert result == Decimal("123.45")

    def test_decimal_to_float(self):
        """Test converting Decimal to float"""
        result = decimal_to_float(Decimal("123.45"))
        assert isinstance(result, float)
        assert result == 123.45


class TestDecimalEncoder:
    """Test the custom JSON encoder for Decimal"""

    def test_decimal_encoder_handles_decimal(self):
        """Test that DecimalEncoder converts Decimal to float"""
        encoder = DecimalEncoder()
        result = encoder.default(Decimal("123.45"))
        assert isinstance(result, float)
        assert result == 123.45

    def test_decimal_encoder_raises_for_unsupported_type(self):
        """Test that DecimalEncoder raises TypeError for unsupported types"""
        encoder = DecimalEncoder()
        with pytest.raises(TypeError):
            encoder.default(object())


class TestJsonDumps:
    """Test the json_dumps wrapper function"""

    def test_json_dumps_handles_decimal(self):
        """Test that json_dumps can serialize Decimal objects"""
        data = {"value": Decimal("123.45"), "nested": {"amount": Decimal("67.89")}}
        result = json_dumps(data)
        assert isinstance(result, str)
        assert "123.45" in result
        assert "67.89" in result

    def test_json_dumps_handles_regular_types(self):
        """Test that json_dumps works with regular types"""
        data = {"string": "test", "number": 42, "boolean": True, "null": None}
        result = json_dumps(data)
        assert isinstance(result, str)
        assert "test" in result
        assert "42" in result
        assert "true" in result
        assert "null" in result

    def test_json_dumps_with_mixed_types(self):
        """Test json_dumps with mixed Decimal and regular types"""
        data = {
            "decimal_value": Decimal("99.99"),
            "int_value": 10,
            "str_value": "hello",
            "list_value": [1, 2, Decimal("3.14")],
        }
        result = json_dumps(data)
        assert "99.99" in result
        assert "10" in result
        assert "hello" in result
        assert "3.14" in result
