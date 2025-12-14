"""Unit tests for UserManager with DynamoDB stubber"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from botocore.exceptions import ClientError
from botocore.stub import ANY

from src.services.user_manager import UserManager
from src.shared.exceptions import ServiceUnavailableError


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
                    "PK": f"USER#{user_id}",
                    "user_id": user_id,
                    "generation": 0,
                    "client_state": "",
                    "created_at": ANY,
                    "updated_at": ANY,
                },
                "ConditionExpression": "attribute_not_exists(PK)",
            },
        )

        user = user_manager.get_or_create_user(user_id)

        assert user.user_id == user_id
        assert user.generation == 0
        assert user.client_state == ""

    def test_get_or_create_user_existing_user(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_datetime_now,
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

        # Stub get_item to return existing user (same client_state as default "")
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"USER#{user_id}"},
                    "user_id": {"S": user_id},
                    "generation": {"N": "5"},
                    "client_state": {"S": ""},
                    "created_at": {"N": str(existing_timestamp)},
                    "updated_at": {"N": str(mock_timestamp)},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"USER#{user_id}"},
            },
        )

        user = user_manager.get_or_create_user(user_id)

        assert user.user_id == user_id
        assert user.generation == 5
        assert user.client_state == ""
        assert user.created_at == datetime.fromtimestamp(existing_timestamp, tz=timezone.utc)

    def test_get_or_create_user_dynamodb_unavailable(
        self,
        user_manager,
        dynamodb_stubber,
        mock_datetime_now,
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
        mock_datetime_now,
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
                    "client_state": {"S": "abc123"},
                    "created_at": {"N": "1234567800.00"},
                    "updated_at": {"N": str(mock_timestamp)},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"USER#{user_id}"},
                "UpdateExpression": "SET generation = generation + :inc, updated_at = :updated_at",
                "ExpressionAttributeValues": {
                    ":inc": 1,
                    ":updated_at": Decimal(str(mock_timestamp)),
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
                    "client_state": {"S": "abc123"},
                    "created_at": {"N": "1234567800.00"},
                    "updated_at": {"N": "1234567890.00"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"USER#{user_id}"},
            },
        )

        assert user_manager.validate_generation(user_id, current_generation) is True

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
                    "client_state": {"S": "abc123"},
                    "created_at": {"N": "1234567800.00"},
                    "updated_at": {"N": "1234567890.00"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"USER#{user_id}"},
            },
        )

        assert user_manager.validate_generation(user_id, token_generation) is False

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
                "Key": {"PK": f"USER#{user_id}"},
            },
        )

        assert user_manager.validate_generation(user_id, 0) is False

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
        mock_timestamp,
        mock_timestamp_datetime,
    ):
        """Test successful user retrieval via get_user"""
        user_id = "user123"

        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"USER#{user_id}"},
                    "user_id": {"S": user_id},
                    "generation": {"N": "3"},
                    "client_state": {"S": "deadbeef"},
                    "created_at": {"N": str(mock_timestamp)},
                    "updated_at": {"N": str(mock_timestamp)},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"USER#{user_id}"},
            },
        )

        user = user_manager.get_user(user_id)

        assert user is not None
        assert user.user_id == user_id
        assert user.generation == 3
        assert user.client_state == "deadbeef"
        assert user.created_at == mock_timestamp_datetime
        assert user.updated_at == mock_timestamp_datetime

    def test_get_user_not_found(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """Test get_user returns None when user doesn't exist"""
        user_id = "nonexistent"

        dynamodb_stubber.add_response(
            "get_item",
            {},  # Empty response
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"USER#{user_id}"},
            },
        )

        assert user_manager.get_user(user_id) is None

    def test_get_or_create_user_unexpected_error(
        self,
        user_manager,
        dynamodb_stubber,
        mock_datetime_now,
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
        """Test that unexpected ClientErrors are re-raised in get_user"""
        from botocore.exceptions import ClientError

        dynamodb_stubber.add_client_error(
            "get_item",
            service_error_code="ValidationException",
            service_message="Unexpected validation error",
        )

        with pytest.raises(ClientError) as exc_info:
            user_manager.get_user("user123")

        assert exc_info.value.response["Error"]["Code"] == "ValidationException"

    def test_increment_generation_unexpected_error(
        self,
        user_manager,
        dynamodb_stubber,
    ):
        """Test that unexpected ClientErrors are re-raised in increment_generation"""

        dynamodb_stubber.add_client_error(
            "update_item",
            service_error_code="ValidationException",
            service_message="Unexpected validation error",
        )

        with pytest.raises(ClientError) as exc_info:
            user_manager.increment_generation("user123")

        assert exc_info.value.response["Error"]["Code"] == "ValidationException"

    def test_get_or_create_user_new_user_with_client_state(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_datetime_now,
        mock_timestamp_datetime,
    ):
        """Test creating a new user with client_state"""
        user_id = "user123"
        client_state = "abc123def456"

        # Stub successful put_item (new user creation with client_state)
        dynamodb_stubber.add_response(
            "put_item",
            {},
            # {
            #     "TableName": storage_table_name,
            #     "Item": {
            #         "PK": {"S": f"USER#{user_id}"},
            #         "user_id": {"S": user_id},
            #         "generation": {"N": "0"},
            #         "client_state": {"S": client_state},
            #         "created_at": {"N": str(mock_timestamp)},
            #         "updated_at": {"N": str(mock_timestamp)},
            #     },
            #     "ConditionExpression": "attribute_not_exists(PK)",
            # },
            {
                "ConditionExpression": "attribute_not_exists(PK)",
                "Item": {
                    "PK": f"USER#{user_id}",
                    "user_id": user_id,
                    "client_state": client_state,
                    "generation": 0,
                    "created_at": Decimal(mock_timestamp),
                    "updated_at": Decimal(mock_timestamp),
                },
                "TableName": "test-storage-table",
            },
        )

        user = user_manager.get_or_create_user(user_id, client_state=client_state)

        assert user.user_id == user_id
        assert user.generation == 0
        assert user.client_state == client_state
        assert user.created_at == mock_timestamp_datetime
        assert user.updated_at == mock_timestamp_datetime

    def test_get_or_create_user_existing_user_same_client_state(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_datetime_now,
    ):
        """Test existing user with same client_state does not increment generation"""
        user_id = "existing_user"
        client_state = "abc123"
        existing_timestamp = 1234567800.00

        # Stub conditional check failure (user already exists)
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="The conditional request failed",
        )

        # Stub get_item to return existing user with same client_state
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"USER#{user_id}"},
                    "user_id": {"S": user_id},
                    "generation": {"N": "5"},
                    "client_state": {"S": client_state},
                    "created_at": {"N": str(existing_timestamp)},
                    "updated_at": {"N": str(mock_timestamp)},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"USER#{user_id}"},
            },
        )

        user = user_manager.get_or_create_user(user_id, client_state=client_state)

        assert user.user_id == user_id
        assert user.generation == 5  # Generation unchanged
        assert user.client_state == client_state
        assert user.created_at == datetime.fromtimestamp(existing_timestamp, tz=timezone.utc)

    def test_get_or_create_user_existing_user_different_client_state(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_datetime_now,
    ):
        """Test existing user with different client_state increments generation"""
        user_id = "existing_user"
        old_client_state = "old_state"
        new_client_state = "new_state"
        existing_timestamp = 1234567800.00

        # Stub conditional check failure (user already exists)
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="The conditional request failed",
        )

        # Stub get_item to return existing user with different client_state
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"USER#{user_id}"},
                    "user_id": {"S": user_id},
                    "generation": {"N": "5"},
                    "client_state": {"S": old_client_state},
                    "created_at": {"N": str(existing_timestamp)},
                    "updated_at": {"N": str(mock_timestamp)},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"USER#{user_id}"},
            },
        )

        # Stub update_item to increment generation and update client_state
        dynamodb_stubber.add_response(
            "update_item",
            {
                "Attributes": {
                    "PK": {"S": f"USER#{user_id}"},
                    "user_id": {"S": user_id},
                    "generation": {"N": "6"},
                    "client_state": {"S": new_client_state},
                    "created_at": {"N": str(existing_timestamp)},
                    "updated_at": {"N": str(mock_timestamp)},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"USER#{user_id}"},
                "UpdateExpression": (
                    "SET generation = generation + :inc, "
                    "client_state = :client_state, "
                    "updated_at = :updated_at"
                ),
                "ExpressionAttributeValues": {
                    ":inc": 1,
                    ":client_state": new_client_state,
                    ":updated_at": Decimal(str(mock_timestamp)),
                },
                "ReturnValues": "ALL_NEW",
            },
        )

        user = user_manager.get_or_create_user(user_id, client_state=new_client_state)

        assert user.user_id == user_id
        assert user.generation == 6  # Generation incremented
        assert user.client_state == new_client_state
        assert user.created_at == datetime.fromtimestamp(existing_timestamp, tz=timezone.utc)
        assert user.updated_at == datetime.fromtimestamp(mock_timestamp, tz=timezone.utc)

    def test_get_or_create_user_client_state_change_dynamodb_unavailable(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_datetime_now,
    ):
        """Test ServiceUnavailableError when DynamoDB fails during client_state update"""
        user_id = "existing_user"
        old_client_state = "old_state"
        new_client_state = "new_state"
        existing_timestamp = 1234567800.00

        # Stub conditional check failure (user already exists)
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="The conditional request failed",
        )

        # Stub get_item to return existing user with different client_state
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"USER#{user_id}"},
                    "user_id": {"S": user_id},
                    "generation": {"N": "5"},
                    "client_state": {"S": old_client_state},
                    "created_at": {"N": str(existing_timestamp)},
                    "updated_at": {"N": str(mock_timestamp)},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"USER#{user_id}"},
            },
        )

        # Stub update_item to fail with DynamoDB error
        dynamodb_stubber.add_client_error(
            "update_item",
            service_error_code="ProvisionedThroughputExceededException",
            service_message="Throughput exceeded",
        )

        with pytest.raises(ServiceUnavailableError) as exc_info:
            user_manager.get_or_create_user(user_id, client_state=new_client_state)

        assert "DynamoDB unavailable" in str(exc_info.value.message)

    def test_get_user_missing_client_state_defaults_to_empty(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
    ):
        """Test get_user returns empty string for missing client_state (legacy records)"""
        user_id = "legacy_user"

        # Stub get_item to return user without client_state field (legacy record)
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"USER#{user_id}"},
                    "user_id": {"S": user_id},
                    "generation": {"N": "3"},
                    # No client_state field - simulating legacy record
                    "created_at": {"N": "1234567800.00"},
                    "updated_at": {"N": "1234567890.00"},
                }
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"USER#{user_id}"},
            },
        )

        user = user_manager.get_user(user_id)

        assert user is not None
        assert user.user_id == user_id
        assert user.client_state == ""  # Default to empty string

    def test_update_user_client_state_unexpected_error(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
    ):
        """Test unexpected ClientError is re-raised in update_user_client_state"""
        user_id = "user123"

        dynamodb_stubber.add_client_error(
            "update_item",
            service_error_code="ValidationException",
            service_message="Unexpected validation error",
        )

        with pytest.raises(ClientError) as exc_info:
            user_manager.update_user_client_state(user_id, "new_state")

        assert exc_info.value.response["Error"]["Code"] == "ValidationException"

    def test_get_or_create_user_exists_but_cannot_retrieve(
        self,
        user_manager,
        dynamodb_stubber,
        storage_table_name,
        mock_timestamp,
        mock_datetime_now,
    ):
        """Test ServiceUnavailableError when user exists but cannot be retrieved"""
        user_id = "user123"

        # Stub conditional check failure (user already exists)
        dynamodb_stubber.add_client_error(
            "put_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="The conditional request failed",
        )

        # Stub get_item to return empty response (user not found, which should be impossible)
        dynamodb_stubber.add_response(
            "get_item",
            {},  # Empty response - no Item
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"USER#{user_id}"},
            },
        )

        with pytest.raises(ServiceUnavailableError) as exc_info:
            user_manager.get_or_create_user(user_id)

        assert "User exists but could not be retrieved" in str(exc_info.value.message)
