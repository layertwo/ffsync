"""Shared test fixtures and configuration"""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.environment.service_provider import ServiceProvider
from src.services.token_generator import TokenGenerator
from src.shared.models import (
    BasicStorageObject,
    BatchResult,
    CollectionData,
)
from tests.fixtures.boto import *  # noqa: F403,F401


@pytest.fixture
def storage_table_name():
    return "test-storage-table"


@pytest.fixture
def token_users_table_name():
    return "test-token-users-table"


@pytest.fixture
def oidc_provider_url():
    return "https://auth.example.com"


@pytest.fixture
def oidc_client_id():
    return "test-client-id"


@pytest.fixture
def base_domain():
    return "sync.example.com"


@pytest.fixture
def token_cache_table_name():
    return "test-token-cache-table"


@pytest.fixture(autouse=True)
def setup_environment(
    monkeypatch,
    aws_region_name,
    aws_access_key_id,
    aws_secret_access_key,
    aws_session_token,
    storage_table_name,
    token_users_table_name,
    token_cache_table_name,
    oidc_provider_url,
    oidc_client_id,
    base_domain,
):
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
def mock_service_provider(boto_session):
    return ServiceProvider()


@pytest.fixture
def mock_storage_manager():
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
def test_user_id():
    """Test user ID for authenticated requests"""
    return "test-user-123"


def make_event_with_auth(event_dict: dict, user_id: str = "test-user-123") -> dict:
    """Helper to add hawk_uid to an event dict"""
    if "requestContext" not in event_dict:
        event_dict["requestContext"] = {}
    event_dict["requestContext"]["hawk_uid"] = user_id
    return event_dict


@pytest.fixture
def sample_lambda_event(test_user_id):
    """Sample Lambda event structure"""
    uid = str(TokenGenerator.generate_uid(test_user_id, 0))
    return {
        "httpMethod": "GET",
        "path": f"/1.5/{uid}/storage/test_collection/test_object",
        "pathParameters": {
            "uid": uid,
            "collectionName": "test_collection",
            "objectId": "test_object",
        },
        "headers": {"Content-Type": "application/json"},
        "body": None,
        "queryStringParameters": None,
        "requestContext": {
            "requestId": "test-request-id",
            "accountId": "123456789012",
            "hawk_uid": test_user_id,
        },
    }


@pytest.fixture
def sample_lambda_context():
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
def sample_bso():
    """Sample BasicStorageObject"""
    return BasicStorageObject(
        id="test_bso",
        payload="test_payload_data",
        modified=1234567890.12,
        sortindex=50,
        ttl=7200,
    )


@pytest.fixture
def sample_collection():
    """Sample CollectionData"""
    return CollectionData(
        name="bookmarks",
        modified=1234567890.12,
        count=10,
        usage=2048,
    )


@pytest.fixture
def sample_batch_result():
    """Sample BatchResult"""
    return BatchResult(
        success=["obj1", "obj2", "obj3"],
        failed={"obj4": ["validation error"]},
        modified=1234567890.12,
    )


@pytest.fixture
def post_event_with_body(test_user_id):
    """Sample POST event with body"""
    uid = str(TokenGenerator.generate_uid(test_user_id, 0))
    return {
        "httpMethod": "POST",
        "path": f"/1.5/{uid}/storage/test_collection",
        "pathParameters": {"uid": uid, "collectionName": "test_collection"},
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"objects": [{"id": "obj1", "payload": "data1", "sortindex": 100}]}),
        "queryStringParameters": None,
    }


@pytest.fixture
def delete_event(test_user_id):
    """Sample DELETE event"""
    uid = str(TokenGenerator.generate_uid(test_user_id, 0))
    return {
        "httpMethod": "DELETE",
        "path": f"/1.5/{uid}/storage/test_collection/test_object",
        "pathParameters": {
            "uid": uid,
            "collectionName": "test_collection",
            "objectId": "test_object",
        },
        "headers": {},
        "body": None,
        "queryStringParameters": None,
    }


# Timestamp fixtures for testing
@pytest.fixture
def mock_timestamp():
    """Mock timestamp value used across tests"""
    return 1234567890.00


@pytest.fixture
def mock_timestamp_datetime(mock_timestamp):
    """Mock timestamp (kept for backwards-compat with existing test sigs)."""
    return mock_timestamp


@pytest.fixture
def mock_datetime_now(mock_timestamp):
    """Mock time.time() for user_manager tests"""
    with patch("src.services.user_manager.time") as mock:
        mock.time.return_value = mock_timestamp
        yield


@pytest.fixture
def mock_get_current_timestamp(mock_timestamp):
    """Mock get_current_timestamp() for storage_manager tests"""
    with patch("src.services.storage_manager.get_current_timestamp", return_value=mock_timestamp):
        yield


@pytest.fixture
def base_url():
    return "sync.example.com"


@pytest.fixture
def storage_domain(base_url):
    return f"storage.{base_url}"


@pytest.fixture
def storage_url(storage_domain):
    return f"https://{storage_domain}"
