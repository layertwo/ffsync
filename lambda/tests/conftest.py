"""Shared test fixtures and configuration"""

import json
from typing import Any, Generator
from unittest.mock import MagicMock, Mock, patch

import boto3
import pytest
from aws_lambda_powertools.event_handler import Response

from src.environment.service_provider import ServiceProvider
from src.shared.models import (
    BasicStorageObject,
    BatchResult,
    CollectionData,
)
from tests.fixtures.boto import *  # noqa: F403,F401


@pytest.fixture
def storage_table_name() -> str:
    return "test-storage-table"


@pytest.fixture
def token_users_table_name() -> str:
    return "test-token-users-table"


@pytest.fixture
def oidc_provider_url() -> str:
    return "https://auth.example.com"


@pytest.fixture
def oidc_client_id() -> str:
    return "test-client-id"


@pytest.fixture
def base_domain() -> str:
    return "sync.example.com"


@pytest.fixture
def token_cache_table_name() -> str:
    return "test-token-cache-table"


@pytest.fixture(autouse=True)
def setup_environment(
    monkeypatch: pytest.MonkeyPatch,
    aws_region_name: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
    aws_session_token: str,
    storage_table_name: str,
    token_users_table_name: str,
    token_cache_table_name: str,
    oidc_provider_url: str,
    oidc_client_id: str,
    base_domain: str,
) -> None:
    """Mock environment variables"""
    monkeypatch.setenv("AWS_REGION", aws_region_name)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", aws_access_key_id)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", aws_secret_access_key)
    monkeypatch.setenv("AWS_SESSION_TOKEN", aws_session_token)
    monkeypatch.setenv("STORAGE_TABLE_NAME", storage_table_name)
    monkeypatch.setenv("TOKEN_USERS_TABLE_NAME", token_users_table_name)
    monkeypatch.setenv("TOKEN_CACHE_TABLE_NAME", token_cache_table_name)
    monkeypatch.setenv("OIDC_PROVIDER_URL", oidc_provider_url)
    monkeypatch.setenv("OIDC_CLIENT_ID", oidc_client_id)
    monkeypatch.setenv("BASE_DOMAIN", base_domain)
    monkeypatch.setenv("CLOCK_SKEW_TOLERANCE", "300")
    monkeypatch.setenv("HAWK_TIMESTAMP_SKEW_TOLERANCE", "60")
    monkeypatch.setenv("RETRY_AFTER_SECONDS", "30")
    monkeypatch.setenv("TOKEN_DURATION", "300")
    monkeypatch.setenv("AUTH_TABLE_NAME", "test-auth-table")
    monkeypatch.setenv("AUTH_SIGNING_KEY_ID", "test-signing-key-id")
    monkeypatch.setenv("CHANNEL_TABLE_NAME", "test-channel-table")


@pytest.fixture
def mock_service_provider(boto_session: boto3.Session) -> ServiceProvider:
    return ServiceProvider()


@pytest.fixture
def mock_storage_manager() -> MagicMock:
    """Mock StorageManager for testing route handlers"""
    manager = MagicMock()

    # Configure common return values
    manager.get_collection.return_value = CollectionData(
        name="test_collection",
        modified=1234567890.12,
        count=5,
        usage=1024,
    )

    manager.get_storage_object.return_value = BasicStorageObject(
        id="test_object",
        payload="test_payload",
        modified=1234567890.12,
        sortindex=100,
        ttl=3600,
    )

    manager.create_or_update_collection.return_value = (
        CollectionData(
            name="test_collection",
            modified=1234567890.12,
            count=1,
            usage=512,
        ),
        BatchResult(
            success=["obj1"],
            failed={},
            modified=1234567890.12,
        ),
    )

    return manager


@pytest.fixture
def test_user_id() -> str:
    """Test user ID for authenticated requests"""
    return "test-user-123"


def json_body(response: Response[Any]) -> Any:
    """Decode a route Response body as JSON. powertools types it Optional; assert once here."""
    assert response.body is not None, f"expected a JSON body, got {response.status_code}"
    return json.loads(response.body)


def header(response: Response[Any], name: str) -> str:
    """Single response header value (powertools types them str | list[str])."""
    value = response.headers[name]
    return value if isinstance(value, str) else value[0]


@pytest.fixture
def sample_lambda_context() -> Mock:
    """Sample Lambda context object"""
    context = Mock()
    context.function_name = "test-function"
    context.function_version = "1"
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
    context.memory_limit_in_mb = "128"
    context.aws_request_id = "test-request-id"
    context.log_group_name = "/aws/lambda/test"
    context.log_stream_name = "2024/01/01/[$LATEST]test"
    return context


@pytest.fixture
def sample_bso() -> BasicStorageObject:
    """Sample BasicStorageObject"""
    return BasicStorageObject(
        id="test_bso",
        payload="test_payload_data",
        modified=1234567890.12,
        sortindex=50,
        ttl=7200,
    )


@pytest.fixture
def sample_collection() -> CollectionData:
    """Sample CollectionData"""
    return CollectionData(
        name="bookmarks",
        modified=1234567890.12,
        count=10,
        usage=2048,
    )


@pytest.fixture
def sample_batch_result() -> BatchResult:
    """Sample BatchResult"""
    return BatchResult(
        success=["obj1", "obj2", "obj3"],
        failed={"obj4": ["validation error"]},
        modified=1234567890.12,
    )


# Timestamp fixtures for testing
@pytest.fixture
def mock_timestamp() -> float:
    """Mock timestamp value used across tests"""
    return 1234567890.00


@pytest.fixture
def mock_datetime_now(mock_timestamp: float) -> Generator[None, None, None]:
    """Mock time.time() for user_manager tests"""
    with patch("src.services.user_manager.time") as mock:
        mock.time.return_value = mock_timestamp
        yield


@pytest.fixture
def mock_get_current_timestamp(mock_timestamp: float) -> Generator[None, None, None]:
    """Mock get_current_timestamp() for storage_manager tests"""
    with patch("src.services.storage_manager.get_current_timestamp", return_value=mock_timestamp):
        yield


@pytest.fixture
def base_url() -> str:
    return "sync.example.com"


@pytest.fixture
def storage_domain(base_url: str) -> str:
    return f"storage.{base_url}"


@pytest.fixture
def storage_url(storage_domain: str) -> str:
    return f"https://{storage_domain}"
