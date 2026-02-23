"""Tests for DeleteAllRootRoute"""

import json
from typing import Any

from src.entrypoint.storage_api import lambda_handler as storage_handler

TEST_USER_ID = "test-user-123"


def build_storage_event(method: str, path: str, user_id: str = TEST_USER_ID) -> dict:
    """Build a storage API event with authentication context"""
    return {
        "httpMethod": method,
        "path": path,
        "pathParameters": None,
        "headers": {},
        "body": None,
        "queryStringParameters": None,
        "requestContext": {
            "requestId": "test-request-id",
            "accountId": "123456789012",
            "authorizer": {"user_id": user_id},
        },
    }


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

        # delete_collection("bookmarks"): query all items
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

        # Delete METADATA
        dynamodb_stubber.add_response("delete_item", {})

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
        """Test handling when user_id is missing from authorizer context"""
        event: dict[str, Any] = {
            "httpMethod": "DELETE",
            "path": "/",
            "pathParameters": None,
            "headers": {},
            "body": None,
            "queryStringParameters": None,
            "requestContext": {"authorizer": {}},
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
