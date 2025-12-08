"""Tests for lambda entrypoint"""

from src.entrypoint import token_api_handler


def test_token_service_happy_path(mock_service_provider, sample_lambda_context):
    """Test happy path for token service"""
    assert token_api_handler({}, sample_lambda_context, mock_service_provider) == {}
