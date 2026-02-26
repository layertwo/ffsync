"""Integration test fixtures and helpers for end-to-end testing"""

import json
import time
from typing import Any, Dict, List, Optional

import pytest

# ============================================================================
# HAWK Authentication Fixtures
# ============================================================================


@pytest.fixture
def valid_hawk_credentials():
    """Valid HAWK credentials for integration tests"""
    return {
        "user_id": "test-user-123",
        "generation": 0,
        "expiry": int(time.time()) + 300,  # 5 minutes from now
        "hawk_id": "dGVzdC11c2VyLTEyMzowOjE3MDIzNDU5Nzg",  # base64: test-user-123:0:1702345978
        "hawk_key": "a" * 64,  # 64-char hex string
    }


@pytest.fixture
def expired_hawk_credentials():
    """Expired HAWK credentials for testing authentication failures"""
    return {
        "user_id": "test-user-123",
        "generation": 0,
        "expiry": int(time.time()) - 100,  # Expired 100 seconds ago
        "hawk_id": "dGVzdC11c2VyLTEyMzowOjE3MDIzNDU4Nzg",
        "hawk_key": "b" * 64,
    }


@pytest.fixture
def hawk_authorization_header(valid_hawk_credentials):
    """Generate a valid HAWK Authorization header"""
    timestamp = int(time.time())
    nonce = "test-nonce-123"
    # Note: In real tests, you'd compute the actual MAC
    # For integration tests, this would be validated by HawkService
    return (
        f'Hawk id="{valid_hawk_credentials["hawk_id"]}", '
        f'ts="{timestamp}", '
        f'nonce="{nonce}", '
        f'mac="test-mac-signature"'
    )


# ============================================================================
# BSO Test Data Fixtures
# ============================================================================


@pytest.fixture
def valid_bso_data():
    """Valid BSO data for creation/update"""
    return {
        "id": "test-bso-001",
        "payload": json.dumps({"title": "Test Bookmark", "url": "https://example.com"}),
        "sortindex": 100,
        "ttl": 3600,
    }


@pytest.fixture
def batch_bso_data():
    """Batch of valid BSOs for batch operations"""
    return [
        {
            "id": f"bso-{i:03d}",
            "payload": json.dumps({"index": i, "data": f"test-data-{i}"}),
            "sortindex": i * 10,
        }
        for i in range(1, 11)  # 10 BSOs
    ]


@pytest.fixture
def large_batch_bso_data():
    """Large batch of BSOs for testing limits (100 items)"""
    return [
        {
            "id": f"bso-{i:03d}",
            "payload": json.dumps({"index": i}),
        }
        for i in range(1, 101)  # 100 BSOs (max limit)
    ]


@pytest.fixture
def oversized_bso_data():
    """BSO with payload exceeding max size (256 KB)"""
    return {
        "id": "oversized-bso",
        "payload": "x" * (256 * 1024 + 1),  # 256 KB + 1 byte
        "sortindex": 100,
    }


# ============================================================================
# Collection Test Data Fixtures
# ============================================================================


@pytest.fixture
def valid_collection_names():
    """List of valid collection names"""
    return [
        "bookmarks",
        "tabs",
        "history",
        "passwords",
        "forms",
        "addons",
        "prefs",
        "clients",
        "crypto",
        "meta",
    ]


@pytest.fixture
def invalid_collection_names():
    """List of invalid collection names for validation testing"""
    return [
        "a" * 33,  # Too long (>32 chars)
        "invalid space",  # Contains space
        "invalid@char",  # Contains @ symbol
        "invalid#char",  # Contains # symbol
        "",  # Empty string
    ]


# ============================================================================
# Lambda Event Builders
# ============================================================================


def build_storage_event(
    method: str,
    path: str,
    user_id: str = "test-user-123",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Any] = None,
    query_params: Optional[Dict[str, str]] = None,
    path_params: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Build a Lambda event for Storage API testing.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        path: Request path (e.g., "/storage/bookmarks/item123")
        user_id: Authenticated user ID (from Lambda Authorizer context)
        headers: HTTP headers
        body: Request body (will be JSON-encoded if dict/list)
        query_params: Query string parameters
        path_params: Path parameters extracted from URL
            Note: Use 'collectionName' and 'id' keys to match route definitions

    Returns:
        Lambda event dictionary
    """
    if headers is None:
        headers = {"Content-Type": "application/json"}

    if body is not None and isinstance(body, (dict, list)):
        body = json.dumps(body)

    merged_params = {"uid": "12345"}
    if path_params:
        merged_params.update(path_params)

    return {
        "httpMethod": method,
        "path": f"/1.5/12345{path}",
        "pathParameters": merged_params,
        "headers": headers,
        "body": body,
        "queryStringParameters": query_params,
        "requestContext": {
            "requestId": "test-request-id",
            "accountId": "123456789012",
            "authorizer": {"user_id": user_id},
        },
    }


def build_authorizer_event(
    method: str,
    path: str,
    authorization_header: str,
    method_arn: str = "arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/storage",
) -> Dict[str, Any]:
    """
    Build a Lambda event for HAWK Authorizer testing.

    Args:
        method: HTTP method
        path: Request path
        authorization_header: HAWK Authorization header value
        method_arn: API Gateway method ARN

    Returns:
        Lambda authorizer event dictionary
    """
    return {
        "type": "REQUEST",
        "methodArn": method_arn,
        "httpMethod": method,  # Required at top level for Lambda Powertools
        "path": path,  # Required at top level for Lambda Powertools
        "headers": {
            "Authorization": authorization_header,
            "Host": "storage.sync.example.com",
        },
        "requestContext": {
            "path": path,
            "httpMethod": method,
            "domainName": "storage.sync.example.com",
        },
    }


# ============================================================================
# DynamoDB Stubber Helpers
# ============================================================================


def stub_get_bso(
    stubber,
    table_name: str,
    user_id: str,
    collection_name: str,
    object_id: str,
    bso_data: Optional[Dict[str, Any]] = None,
    exists: bool = True,
):
    """
    Stub a DynamoDB get_item call for retrieving a BSO.

    Args:
        stubber: botocore.stub.Stubber instance
        table_name: DynamoDB table name
        user_id: User ID
        collection_name: Collection name
        object_id: BSO ID
        bso_data: BSO data to return (if exists=True)
        exists: Whether the BSO exists
    """
    pk = f"USER#{user_id}#COLLECTION#{collection_name}"
    sk = f"OBJECT#{object_id}"

    if exists and bso_data:
        response = {
            "Item": {
                "PK": {"S": pk},
                "SK": {"S": sk},
                "id": {"S": bso_data.get("id", object_id)},
                "payload": {"S": bso_data.get("payload", "")},
                "modified": {"N": str(bso_data.get("modified", 1234567890.12))},
            }
        }
        if "sortindex" in bso_data:
            response["Item"]["sortindex"] = {"N": str(bso_data["sortindex"])}
        if "ttl" in bso_data:
            response["Item"]["ttl"] = {"N": str(bso_data["ttl"])}
    else:
        response = {}

    stubber.add_response(
        "get_item",
        response,
        {"TableName": table_name, "Key": {"PK": {"S": pk}, "SK": {"S": sk}}},
    )


def stub_put_bso(
    stubber,
    table_name: str,
    user_id: str,
    collection_name: str,
    object_id: str,
):
    """
    Stub a DynamoDB put_item call for creating/updating a BSO.

    Args:
        stubber: botocore.stub.Stubber instance
        table_name: DynamoDB table name
        user_id: User ID
        collection_name: Collection name
        object_id: BSO ID
    """
    # Note: We use ANY for the Item parameter since it's complex
    # In real tests, you'd match the exact structure
    stubber.add_response(
        "put_item",
        {},
        expected_params={
            "TableName": table_name,
            # Item structure is complex, so we don't match it exactly
        },
    )


def stub_query_collection(
    stubber,
    table_name: str,
    user_id: str,
    collection_name: str,
    items: List[Dict[str, Any]],
):
    """
    Stub a DynamoDB query call for listing BSOs in a collection.

    Args:
        stubber: botocore.stub.Stubber instance
        table_name: DynamoDB table name
        user_id: User ID
        collection_name: Collection name
        items: List of BSO items to return
    """
    pk = f"USER#{user_id}#COLLECTION#{collection_name}"

    response_items = []
    for item in items:
        dynamo_item = {
            "PK": {"S": pk},
            "SK": {"S": f"OBJECT#{item['id']}"},
            "id": {"S": item["id"]},
            "payload": {"S": item.get("payload", "")},
            "modified": {"N": str(item.get("modified", 1234567890.12))},
        }
        if "sortindex" in item:
            dynamo_item["sortindex"] = {"N": str(item["sortindex"])}
        response_items.append(dynamo_item)

    stubber.add_response(
        "query",
        {"Items": response_items, "Count": len(response_items)},
        expected_params={
            "TableName": table_name,
            # Query parameters are complex, so we don't match exactly
        },
    )


# ============================================================================
# Response Validation Helpers
# ============================================================================


def assert_successful_response(response: Dict[str, Any], expected_status: int = 200):
    """Assert that a Lambda response is successful"""
    assert response["statusCode"] == expected_status
    assert "headers" in response
    assert "X-Weave-Timestamp" in response["headers"]


def assert_error_response(
    response: Dict[str, Any],
    expected_status: int,
    expected_code: Optional[int] = None,
):
    """
    Assert that a Lambda response is an error.

    Args:
        response: Lambda response dictionary
        expected_status: Expected HTTP status code
        expected_code: Expected Mozilla response code (if applicable)
    """
    assert response["statusCode"] == expected_status

    if expected_code is not None:
        body = json.loads(response["body"])
        assert body == expected_code


def assert_bso_response(response: Dict[str, Any], expected_bso: Dict[str, Any]):
    """Assert that a response contains the expected BSO"""
    assert_successful_response(response)

    body = json.loads(response["body"])
    assert body["id"] == expected_bso["id"]
    assert body["payload"] == expected_bso["payload"]
    assert "modified" in body

    # TTL should NOT be in response (write-only field)
    assert "ttl" not in body

    # X-Last-Modified header should match modified field
    assert "X-Last-Modified" in response["headers"]
    assert float(response["headers"]["X-Last-Modified"]) == body["modified"]


def assert_collection_response(
    response: Dict[str, Any],
    expected_ids: List[str],
    full: bool = False,
):
    """
    Assert that a response contains the expected collection data.

    Args:
        response: Lambda response dictionary
        expected_ids: Expected BSO IDs in the collection
        full: Whether full BSO objects are expected (vs just IDs)
    """
    assert_successful_response(response)

    body = json.loads(response["body"])
    assert isinstance(body, list)

    if full:
        # Full BSO objects
        assert len(body) == len(expected_ids)
        returned_ids = [bso["id"] for bso in body]
        assert set(returned_ids) == set(expected_ids)

        # Verify TTL is not in any BSO
        for bso in body:
            assert "ttl" not in bso
    else:
        # Just IDs
        assert set(body) == set(expected_ids)


def assert_batch_response(
    response: Dict[str, Any],
    expected_success: List[str],
    expected_failed: Optional[Dict[str, str]] = None,
):
    """Assert that a batch operation response is correct"""
    assert_successful_response(response)

    body = json.loads(response["body"])
    assert "modified" in body
    assert "success" in body
    assert "failed" in body

    assert set(body["success"]) == set(expected_success)

    if expected_failed:
        assert body["failed"] == expected_failed
    else:
        assert body["failed"] == {}


# ============================================================================
# User Isolation Test Helpers
# ============================================================================


@pytest.fixture
def multi_user_test_data():
    """Test data for multiple users to verify isolation"""
    return {
        "user1": {
            "user_id": "user-001",
            "collections": {
                "bookmarks": [
                    {"id": "bm1", "payload": json.dumps({"url": "https://user1.com"})},
                    {"id": "bm2", "payload": json.dumps({"url": "https://user1-2.com"})},
                ],
                "tabs": [
                    {"id": "tab1", "payload": json.dumps({"url": "https://tab1.com"})},
                ],
            },
        },
        "user2": {
            "user_id": "user-002",
            "collections": {
                "bookmarks": [
                    {"id": "bm1", "payload": json.dumps({"url": "https://user2.com"})},
                ],
                "history": [
                    {"id": "hist1", "payload": json.dumps({"url": "https://history.com"})},
                ],
            },
        },
    }


# ============================================================================
# Timestamp Test Helpers
# ============================================================================


def assert_timestamp_format(timestamp_str: str):
    """Assert that a timestamp string has the correct format (2 decimal places)"""
    parts = timestamp_str.split(".")
    assert len(parts) == 2, "Timestamp must have decimal point"
    assert len(parts[1]) == 2, "Timestamp must have exactly 2 decimal places"

    # Verify it's a valid float
    timestamp = float(timestamp_str)
    assert timestamp > 0, "Timestamp must be positive"


def assert_timestamp_headers(response: Dict[str, Any], is_write: bool = False):
    """
    Assert that timestamp headers are present and correct.

    Args:
        response: Lambda response dictionary
        is_write: Whether this is a write operation (X-Weave-Timestamp == X-Last-Modified)
    """
    headers = response["headers"]

    # X-Weave-Timestamp must always be present
    assert "X-Weave-Timestamp" in headers
    assert_timestamp_format(headers["X-Weave-Timestamp"])

    if is_write:
        # For writes, X-Last-Modified must equal X-Weave-Timestamp
        assert "X-Last-Modified" in headers
        assert headers["X-Last-Modified"] == headers["X-Weave-Timestamp"]
