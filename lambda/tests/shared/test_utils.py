"""Tests for shared utility functions"""

import re

from aws_lambda_powertools.utilities.data_classes import APIGatewayProxyEvent

from src.shared.utils import (
    extract_hawk_request_params,
    get_weave_timestamp,
)


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
