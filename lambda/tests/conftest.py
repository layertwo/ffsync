"""Shared test fixtures and configuration"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.environment.service_provider import ServiceProvider
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
def oidc_secret_arn():
    return "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-oidc-config"


@pytest.fixture
def base_domain():
    return "sync.example.com"


@pytest.fixture(autouse=True)
def setup_environment(
    monkeypatch,
    aws_region_name,
    aws_access_key_id,
    aws_secret_access_key,
    aws_session_token,
    storage_table_name,
    token_users_table_name,
    oidc_secret_arn,
    base_domain,
):
    """Mock environment variables"""
    monkeypatch.setenv("AWS_REGION", aws_region_name)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", aws_access_key_id)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", aws_secret_access_key)
    monkeypatch.setenv("AWS_SESSION_TOKEN", aws_session_token)
    monkeypatch.setenv("STORAGE_TABLE_NAME", storage_table_name)
    monkeypatch.setenv("TOKEN_USERS_TABLE_NAME", token_users_table_name)
    monkeypatch.setenv("OIDC_SECRET_ARN", oidc_secret_arn)
    monkeypatch.setenv("BASE_DOMAIN", base_domain)


class MockServiceProvider(ServiceProvider):
    def __init__(self, boto_session):
        """
        Args:
            boto_session: The test boto3.Session
        """
        self._mock_session = boto_session

    @property
    def session(self):
        """Override to return test session"""
        return self._mock_session


@pytest.fixture
def mock_service_provider(boto_session):
    """
    Fixture providing MockServiceProvider with stubbed AWS clients.

    The secretsmanager_client is injected into the provider's __dict__,
    bypassing the @cached_property so the stubbed client is used.

    Usage:
        def test_integration(mock_service_provider, secretsmanager_stubber):
            # Add stubbed Secrets Manager responses
            secretsmanager_stubber.add_response('get_secret_value', {...})

            # Pass directly to lambda handler
            result = lambda_handler(event, context, service_provider=mock_service_provider)
    """
    return MockServiceProvider(boto_session)


@pytest.fixture
def mock_storage_manager():
    """Mock StorageManager for testing route handlers"""
    manager = MagicMock()

    # Configure common return values
    manager.get_collection.return_value = CollectionData(
        name="test_collection",
        modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
        count=5,
        usage=1024,
    )

    manager.get_storage_object.return_value = BasicStorageObject(
        id="test_object",
        payload="test_payload",
        modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
        sortindex=100,
        ttl=3600,
    )

    manager.create_or_update_collection.return_value = (
        CollectionData(
            name="test_collection",
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
            count=1,
            usage=512,
        ),
        BatchResult(
            success=["obj1"],
            failed={},
            modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
        ),
    )

    return manager


@pytest.fixture
def sample_lambda_event():
    """Sample Lambda event structure"""
    return {
        "httpMethod": "GET",
        "path": "/storage/test_collection/test_object",
        "pathParameters": {
            "collectionName": "test_collection",
            "objectId": "test_object",
        },
        "headers": {"Content-Type": "application/json"},
        "body": None,
        "queryStringParameters": None,
        "requestContext": {"requestId": "test-request-id", "accountId": "123456789012"},
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
        modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
        sortindex=50,
        ttl=7200,
    )


@pytest.fixture
def sample_collection():
    """Sample CollectionData"""
    return CollectionData(
        name="bookmarks",
        modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
        count=10,
        usage=2048,
    )


@pytest.fixture
def sample_batch_result():
    """Sample BatchResult"""
    return BatchResult(
        success=["obj1", "obj2", "obj3"],
        failed={"obj4": ["validation error"]},
        modified=datetime.fromtimestamp(1234567890.12, tz=timezone.utc),
    )


@pytest.fixture
def post_event_with_body():
    """Sample POST event with body"""
    return {
        "httpMethod": "POST",
        "path": "/storage/test_collection",
        "pathParameters": {"collectionName": "test_collection"},
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"objects": [{"id": "obj1", "payload": "data1", "sortindex": 100}]}),
        "queryStringParameters": None,
    }


@pytest.fixture
def delete_event():
    """Sample DELETE event"""
    return {
        "httpMethod": "DELETE",
        "path": "/storage/test_collection/test_object",
        "pathParameters": {
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
    """Mock timestamp as datetime object"""
    return datetime.fromtimestamp(mock_timestamp, tz=timezone.utc)


@pytest.fixture
def mock_datetime_now(mock_timestamp):
    """Mock datetime.now() for user_manager tests"""
    mock_dt = datetime.fromtimestamp(mock_timestamp, tz=timezone.utc)
    with patch("src.services.user_manager.datetime") as mock:
        mock.now.return_value = mock_dt
        mock.fromtimestamp = datetime.fromtimestamp
        yield


@pytest.fixture
def mock_get_current_timestamp(mock_timestamp):
    """Mock get_current_timestamp() for storage_manager tests"""
    with patch("src.services.storage_manager.get_current_timestamp", return_value=mock_timestamp):
        yield
