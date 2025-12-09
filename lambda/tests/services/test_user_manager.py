"""Unit tests for UserManager with DynamoDB stubber"""

from unittest.mock import patch

import pytest

from src.services.user_manager import UserManager
from src.shared.exceptions import ServiceUnavailableError


@pytest.fixture
def mock_timestamp():
    return 1234567890.12


@pytest.fixture
def mock_get_current_timestamp(mock_timestamp):
    with patch("src.services.user_manager.get_current_timestamp", return_value=mock_timestamp):
        yield


class TestUserManager:
    """Test UserManager DynamoDB operations"""

    @pytest.fixture
    def user_manager(self, dynamodb_table):
        """Create UserManager instance with stubbed table"""
        return UserManager(table=dynamodb_table)

    def test_get_or_create_user_new_user(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test creating a new user when user doesn't exist"""
        user_id = "user123"

        # Stub successful put_item (new user creation)
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": {"S": f"USER#{user_id}"},
                    "user_id": {"S": user_id},
                    "generation": {"N": "0"},
                    "created_at": {"N": str(mock_timestamp)},
                    "updated_at": {"N": str(mock_timestamp)},
                },
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        user = user_manager.get_or_create_user(user_id)

        assert user.user_id == user_id
        assert user.generation == 0
        assert user.created_at == mock_timestamp
        assert user.updated_at == mock_timestamp

    def test_get_or_create_user_existing_user(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test retrieving existing user when conditional write fails"""
        user_id = "existing_user"
        existing_timestamp = 1234567800.00

        # Stub conditional check failure (user already exists)
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="The conditional request failed",
        )

        # Stub get_item to return existing user
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"USER#{user_id}"},
                    "user_id": {"S": user_id},
                    "generation": {"N": "5"},
                    "created_at": {"N": str(existing_timestamp)},
                    "updated_at": {"N": str(mock_timestamp)},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": {"S": f"USER#{user_id}"}},
            },
        )

        user = user_manager.get_or_create_user(user_id)

        assert user.user_id == user_id
        assert user.generation == 5
        assert user.created_at == existing_timestamp

    def test_get_or_create_user_dynamodb_unavailable(
        self,
        user_manager,
        dynamodb_stubber,
        mock_get_current_timestamp,
    ):
        """Test ServiceUnavailableError when DynamoDB is unavailable"""
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ProvisionedThroughputExceededException",
            service_message="Throughput exceeded",
        )

        with pytest.raises(ServiceUnavailableError) as exc_info:
            user_manager.get_or_create_user("user123")

        assert "DynamoDB unavailable" in str(exc_info.value.message)

    def test_increment_generation_success(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_get_current_timestamp,
    ):
        """Test successful generation increment"""
        user_id = "user123"

        dynamodb_stubber.add_response(
            "update_item",
            {
                "Attributes": {
                    "PK": {"S": f"USER#{user_id}"},
                    "user_id": {"S": user_id},
                    "generation": {"N": "6"},
                    "created_at": {"N": "1234567800.00"},
                    "updated_at": {"N": str(mock_timestamp)},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": {"S": f"USER#{user_id}"}},
                "UpdateExpression": "SET generation = generation + :inc, updated_at = :updated_at",
                "ExpressionAttributeValues": {
                    ":inc": {"N": "1"},
                    ":updated_at": {"N": str(mock_timestamp)},
                },
                "ReturnValues": "ALL_NEW",
            },
        )

        new_generation = user_manager.increment_generation(user_id)

        assert new_generation == 6

    def test_increment_generation_dynamodb_unavailable(
        self,
        user_manager,
        dynamodb_stubber,
        mock_get_current_timestamp,
    ):
        """Test ServiceUnavailableError when DynamoDB is unavailable during increment"""
        dynamodb_stubber.add_client_error(
            "update_item",
            service_error_code="InternalServerError",
            service_message="Internal error",
        )

        with pytest.raises(ServiceUnavailableError) as exc_info:
            user_manager.increment_generation("user123")

        assert "DynamoDB unavailable" in str(exc_info.value.message)

    def test_validate_generation_valid(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """Test generation validation when generation matches"""
        user_id = "user123"
        current_generation = 5

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"USER#{user_id}"},
                    "user_id": {"S": user_id},
                    "generation": {"N": str(current_generation)},
                    "created_at": {"N": "1234567800.00"},
                    "updated_at": {"N": "1234567890.00"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": {"S": f"USER#{user_id}"}},
            },
        )

        is_valid = user_manager.validate_generation(user_id, current_generation)

        assert is_valid is True

    def test_validate_generation_invalid(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """Test generation validation when generation doesn't match"""
        user_id = "user123"
        stored_generation = 5
        token_generation = 3  # Outdated

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"USER#{user_id}"},
                    "user_id": {"S": user_id},
                    "generation": {"N": str(stored_generation)},
                    "created_at": {"N": "1234567800.00"},
                    "updated_at": {"N": "1234567890.00"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": {"S": f"USER#{user_id}"}},
            },
        )

        is_valid = user_manager.validate_generation(user_id, token_generation)

        assert is_valid is False

    def test_validate_generation_user_not_found(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """Test generation validation when user doesn't exist"""
        user_id = "nonexistent_user"

        dynamodb_stubber.add_response(
            "get_item",
            {},  # Empty response - no Item
            {
                "TableName": storage_table_name,
                "Key": {"PK": {"S": f"USER#{user_id}"}},
            },
        )

        is_valid = user_manager.validate_generation(user_id, 0)

        assert is_valid is False

    def test_validate_generation_dynamodb_unavailable(
        self,
        user_manager,
        dynamodb_stubber,
    ):
        """Test ServiceUnavailableError when DynamoDB is unavailable during validation"""
        dynamodb_stubber.add_client_error(
            "get_item",
            service_error_code="RequestLimitExceeded",
            service_message="Request limit exceeded",
        )

        with pytest.raises(ServiceUnavailableError) as exc_info:
            user_manager.validate_generation("user123", 0)

        assert "DynamoDB unavailable" in str(exc_info.value.message)

    def test_get_user_success(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """Test successful user retrieval via _get_user"""
        user_id = "user123"

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"USER#{user_id}"},
                    "user_id": {"S": user_id},
                    "generation": {"N": "3"},
                    "created_at": {"N": "1234567800.00"},
                    "updated_at": {"N": "1234567890.00"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": {"S": f"USER#{user_id}"}},
            },
        )

        user = user_manager._get_user(user_id)

        assert user is not None
        assert user.user_id == user_id
        assert user.generation == 3
        assert user.created_at == 1234567800.00
        assert user.updated_at == 1234567890.00

    def test_get_user_not_found(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """Test _get_user returns None when user doesn't exist"""
        user_id = "nonexistent"

        dynamodb_stubber.add_response(
            "get_item",
            {},  # Empty response
            {
                "TableName": storage_table_name,
                "Key": {"PK": {"S": f"USER#{user_id}"}},
            },
        )

        user = user_manager._get_user(user_id)

        assert user is None

    def test_get_or_create_user_unexpected_error(
        self,
        user_manager,
        dynamodb_stubber,
        mock_get_current_timestamp,
    ):
        """Test that unexpected ClientErrors are re-raised in get_or_create_user"""
        from botocore.exceptions import ClientError

        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ValidationException",
            service_message="Unexpected validation error",
        )

        with pytest.raises(ClientError) as exc_info:
            user_manager.get_or_create_user("user123")

        assert exc_info.value.response["Error"]["Code"] == "ValidationException"

    def test_get_user_unexpected_error(
        self,
        user_manager,
        dynamodb_stubber,
    ):
        """Test that unexpected ClientErrors are re-raised in _get_user"""
        from botocore.exceptions import ClientError

        dynamodb_stubber.add_client_error(
            "get_item",
            service_error_code="ValidationException",
            service_message="Unexpected validation error",
        )

        with pytest.raises(ClientError) as exc_info:
            user_manager._get_user("user123")

        assert exc_info.value.response["Error"]["Code"] == "ValidationException"

    def test_increment_generation_unexpected_error(
        self,
        user_manager,
        dynamodb_stubber,
        mock_get_current_timestamp,
    ):
        """Test that unexpected ClientErrors are re-raised in increment_generation"""
        from botocore.exceptions import ClientError

        dynamodb_stubber.add_client_error(
            "update_item",
            service_error_code="ValidationException",
            service_message="Unexpected validation error",
        )

        with pytest.raises(ClientError) as exc_info:
            user_manager.increment_generation("user123")

        assert exc_info.value.response["Error"]["Code"] == "ValidationException"
