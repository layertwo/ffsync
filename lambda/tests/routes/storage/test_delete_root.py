"""Tests for DeleteAllRootRoute"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.entrypoint.storage_api import lambda_handler as storage_handler
from src.routes.storage.delete_root import DeleteAllRootRoute
from src.services.hawk_service import HawkCredentials
from src.services.token_generator import TokenGenerator

TEST_USER_ID = "test-user-123"
TEST_GENERATION = 0
TEST_UID = str(TokenGenerator.generate_uid(TEST_USER_ID, TEST_GENERATION))


def build_storage_event(method: str, path: str, user_id: str = TEST_USER_ID) -> dict:
    """Build a storage API event with authentication context"""
    return {
        "httpMethod": method,
        "path": f"/1.5/{TEST_UID}{path}",
        "pathParameters": {"uid": TEST_UID},
        "headers": {"Authorization": 'Hawk id="test", mac="test"'},
        "body": None,
        "queryStringParameters": None,
        "requestContext": {
            "requestId": "test-request-id",
            "accountId": "123456789012",
            "domainName": "storage.example.com",
        },
    }


@pytest.fixture(autouse=True)
def mock_hawk_validate(mock_service_provider):
    """Mock hawk_service.validate to bypass Hawk auth in storage handler tests."""
    creds = HawkCredentials(
        user_id=TEST_USER_ID,
        generation=TEST_GENERATION,
        expiry=9999999999,
        hawk_id="test-hawk-id",
    )
    with patch.object(mock_service_provider.hawk_service, "validate", return_value=creds):
        yield


class TestDeleteAllRootRoute:
    """Tests for DeleteAllRootRoute"""

    def test_handle_success(self, mock_service_provider, dynamodb_stubber, sample_lambda_context):
        """Test successful deletion of all storage via root endpoint"""
        event = build_storage_event(method="DELETE", path="/")

        # list_collections: GSI query returns one collection
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": f"USER#{TEST_USER_ID}#COLLECTION#bookmarks"},
                        "SK": {"S": "METADATA"},
                        "user_id": {"S": TEST_USER_ID},
                        "name": {"S": "bookmarks"},
                        "modified": {"N": "1234567880.00"},
                        "count": {"N": "1"},
                        "usage": {"N": "100"},
                    }
                ]
            },
        )

        # delete_collection("bookmarks"): verify exists
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"USER#{TEST_USER_ID}#COLLECTION#bookmarks"},
                    "SK": {"S": "METADATA"},
                    "name": {"S": "bookmarks"},
                    "modified": {"N": "1234567880.00"},
                    "count": {"N": "1"},
                    "usage": {"N": "100"},
                }
            },
        )

        # delete_collection("bookmarks"): query all items (with ProjectionExpression)
        dynamodb_stubber.add_response(
            "query",
            {
                "Items": [
                    {
                        "PK": {"S": f"USER#{TEST_USER_ID}#COLLECTION#bookmarks"},
                        "SK": {"S": "METADATA"},
                    },
                ]
            },
        )

        # batch_writer deletes METADATA via batch_write_item
        dynamodb_stubber.add_response("batch_write_item", {"UnprocessedItems": {}})

        response = storage_handler(event, sample_lambda_context, mock_service_provider)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "modified" in body
        assert isinstance(body["modified"], (int, float))

    def test_handle_with_empty_storage(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """Test deletion when storage is already empty"""
        event = build_storage_event(method="DELETE", path="/")

        # list_collections: GSI query returns no collections
        dynamodb_stubber.add_response("query", {"Items": []})

        response = storage_handler(event, sample_lambda_context, mock_service_provider)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "modified" in body

    def test_handle_unauthorized_missing_user_id(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """Test handling when hawk_uid is missing (no auth header -> middleware rejects)"""
        event: dict[str, Any] = {
            "httpMethod": "DELETE",
            "path": f"/1.5/{TEST_UID}",
            "pathParameters": {"uid": TEST_UID},
            "headers": {},
            "body": None,
            "queryStringParameters": None,
            "requestContext": {},
        }

        response = storage_handler(event, sample_lambda_context, mock_service_provider)

        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert body["error"] == "Unauthorized"

    def test_root_and_storage_endpoints_behave_identically(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """Test that DELETE / and DELETE /storage behave the same way"""
        # Test DELETE / — empty storage
        root_event = build_storage_event(method="DELETE", path="/")
        dynamodb_stubber.add_response("query", {"Items": []})
        root_response = storage_handler(root_event, sample_lambda_context, mock_service_provider)

        # Test DELETE /storage — empty storage
        storage_event = build_storage_event(method="DELETE", path="/storage")
        dynamodb_stubber.add_response("query", {"Items": []})
        storage_response = storage_handler(
            storage_event, sample_lambda_context, mock_service_provider
        )

        # Both should return 200 with modified timestamp
        assert root_response["statusCode"] == 200
        assert storage_response["statusCode"] == 200

        root_body = json.loads(root_response["body"])
        storage_body = json.loads(storage_response["body"])

        assert "modified" in root_body
        assert "modified" in storage_body

    def test_handle_internal_error(
        self, mock_service_provider, dynamodb_stubber, sample_lambda_context
    ):
        """Test handling of internal server errors"""
        event = build_storage_event(method="DELETE", path="/")

        # Stub GSI query (list_collections) to raise an exception
        dynamodb_stubber.add_client_error("query", service_error_code="InternalServerError")

        response = storage_handler(event, sample_lambda_context, mock_service_provider)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"] == "Internal server error"


class TestDeleteAllRootRouteUnit:
    """Unit tests for DeleteAllRootRoute.handle() called directly (bypassing middleware)"""

    def test_missing_user_id_returns_401(self):
        """Route returns 401 when hawk_uid is not in requestContext."""
        route = DeleteAllRootRoute(storage_manager=MagicMock())
        event: dict = {
            "requestContext": {},
        }
        response = route.handle(event)
        assert response.status_code == 401
        body = json.loads(response.body)  # type: ignore[arg-type]
        assert body["error"] == "Unauthorized"
