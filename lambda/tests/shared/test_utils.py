"""Tests for shared utility functions"""

import re
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.shared.utils import (
    DecimalEncoder,
    datetime_decoder,
    datetime_encoder,
    decimal_to_float,
    extract_hawk_request_params,
    float_to_decimal,
    get_weave_timestamp,
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


class TestWeaveTimestamp:
    """Test Weave timestamp generation (Requirements 9.1, 9.2)"""

    def test_get_weave_timestamp_format(self):
        """Test that get_weave_timestamp returns correct format"""
        timestamp = get_weave_timestamp()

        # Should be a string
        assert isinstance(timestamp, str)

        # Should match format: digits.2decimals (e.g., "1702345678.12")
        assert re.match(r"^\d+\.\d{2}$", timestamp), f"Timestamp {timestamp} doesn't match format"

        # Should be parseable as float
        float_value = float(timestamp)
        assert float_value > 0

    def test_get_weave_timestamp_precision(self):
        """Test that get_weave_timestamp has exactly 2 decimal places"""
        timestamp = get_weave_timestamp()

        # Split on decimal point
        parts = timestamp.split(".")
        assert len(parts) == 2, "Timestamp should have exactly one decimal point"
        assert len(parts[1]) == 2, "Timestamp should have exactly 2 decimal places"


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


class TestExtractHawkRequestParams:
    """Test extract_hawk_request_params helper"""

    def test_extracts_domain_name_from_request_context(self):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/oauth/token",
                "headers": {"host": "wrong.example.com"},
                "requestContext": {"domainName": "auth.prod.ffsync.layertwo.dev"},
            }
        )
        method, path, host, port = extract_hawk_request_params(event)
        assert method == "POST"
        assert path == "/v1/oauth/token"
        assert host == "auth.prod.ffsync.layertwo.dev"
        assert port == 443

    def test_appends_query_string_to_path(self):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "POST",
                "path": "/v1/session/destroy",
                "headers": {},
                "queryStringParameters": {"service": "sync"},
                "requestContext": {"domainName": "auth.example.com"},
            }
        )
        method, path, host, port = extract_hawk_request_params(event)
        assert path == "/v1/session/destroy?service=sync"

    def test_falls_back_to_host_header_when_no_request_context(self):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/session/status",
                "headers": {"host": "fallback.example.com"},
            }
        )
        method, path, host, port = extract_hawk_request_params(event)
        assert host == "fallback.example.com"

    def test_falls_back_to_localhost_when_no_host_or_context(self):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/session/status",
                "headers": {},
            }
        )
        method, path, host, port = extract_hawk_request_params(event)
        assert host == "localhost"

    def test_no_query_string_when_none(self):
        event = APIGatewayProxyEvent(
            {
                "httpMethod": "GET",
                "path": "/v1/session/status",
                "headers": {},
                "queryStringParameters": None,
                "requestContext": {"domainName": "auth.example.com"},
            }
        )
        _, path, _, _ = extract_hawk_request_params(event)
        assert path == "/v1/session/status"
