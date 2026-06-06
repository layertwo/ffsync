"""User manager for DynamoDB operations on token server users"""

import time
from decimal import Decimal
from typing import List, Optional

from botocore.exceptions import ClientError

from src.shared.exceptions import InvalidClientStateError, ServiceUnavailableError
from src.shared.user import UserRecord

_PK = "PK"
PK_PREFIX = "USER"
MAX_CLIENT_STATE_HISTORY = 50


class UserManager:
    """Manages user operations with DynamoDB for the Token Server"""

    def __init__(self, table):
        """Initialize UserManager

        Args:
            table: DynamoDB Table resource
        """
        self.table = table

    def _user_pk(self, user_id: str) -> str:
        """Generate partition key for user record

        Args:
            user_id: User identifier from OIDC sub claim (stable)

        Returns:
            Partition key string
        """
        return f"{PK_PREFIX}#{user_id}"

    def create_user(self, user_id: str, client_state: str = "") -> UserRecord:
        """Create a new user record with generation 0

        Uses conditional write to ensure atomicity. Raises ConditionalCheckFailedException
        if the user already exists.

        Args:
            user_id: User identifier from OIDC sub claim (stable)
            client_state: X-Client-State header value (urlsafe-base64 + period, max 32 chars)

        Returns:
            UserRecord with generation 0 and empty client_state_history

        Raises:
            ClientError: If user already exists (ConditionalCheckFailedException)
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        current_time = time.time()

        try:

            user_record = UserRecord(
                user_id=user_id,
                generation=0,
                client_state=client_state,
                client_state_history=[],
                created_at=current_time,
                updated_at=current_time,
            )

            self.table.put_item(
                Item=user_record.to_item(),
                ConditionExpression="attribute_not_exists(PK)",
            )

            return user_record

        except ClientError as e:
            if e.response["Error"]["Code"] in (
                "ResourceNotFoundException",
                "ProvisionedThroughputExceededException",
                "RequestLimitExceeded",
                "InternalServerError",
            ):
                raise ServiceUnavailableError(
                    f"DynamoDB unavailable: {e.response['Error']['Code']}"
                )
            raise

    def get_user(self, user_id: str) -> Optional[UserRecord]:
        """Get user record from DynamoDB

        Args:
            user_id: User identifier from OIDC sub claim (stable)

        Returns:
            UserRecord if found, None otherwise

        Raises:
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        pk = self._user_pk(user_id)

        try:
            response = self.table.get_item(
                Key={_PK: pk},
            )

            if "Item" not in response:
                return None

            item = response["Item"]
            # Provide defaults for missing fields (legacy records migration)
            if "client_state" not in item:
                item["client_state"] = ""
            if "client_state_history" not in item:
                item["client_state_history"] = []
            return UserRecord.model_validate(item)

        except ClientError as e:
            if e.response["Error"]["Code"] in (
                "ResourceNotFoundException",
                "ProvisionedThroughputExceededException",
                "RequestLimitExceeded",
                "InternalServerError",
            ):
                raise ServiceUnavailableError(
                    f"DynamoDB unavailable: {e.response['Error']['Code']}"
                )
            raise

    def validate_client_state(self, user_record: UserRecord, client_state: str) -> None:
        """Validate client state against history.

        Per Mozilla spec, the following client state transitions are rejected:
        1. New client_state matches any value in client_state_history
        2. New client_state is empty but client_state_history contains non-empty values

        Args:
            user_record: Existing user record with client_state_history
            client_state: New X-Client-State value to validate

        Raises:
            InvalidClientStateError: If client state transition is invalid
        """
        # Check if new client_state matches any previously-seen value
        if client_state in user_record.client_state_history:
            raise InvalidClientStateError(
                "Client state has been previously used and cannot be reused"
            )

        # Check if new client_state is empty but history contains non-empty values
        if client_state == "" and any(state != "" for state in user_record.client_state_history):
            raise InvalidClientStateError(
                "Cannot revert to empty client state after using non-empty values"
            )

    def update_user_client_state(
        self,
        user_id: str,
        client_state: str,
        previous_client_state: str,
        current_history: List[str],
    ) -> UserRecord:
        """Update client state, add previous to history, and increment generation atomically

        The history is capped at MAX_CLIENT_STATE_HISTORY entries. When the cap is reached,
        the oldest entry is dropped to make room for the new one.

        Args:
            user_id: User identifier from OIDC sub claim (stable)
            client_state: New X-Client-State value
            previous_client_state: Previous X-Client-State value to add to history
            current_history: The current client_state_history from the stored user record

        Returns:
            Updated UserRecord with new generation, client_state, and updated history

        Raises:
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        pk = self._user_pk(user_id)
        current_time = time.time()
        new_history = (current_history + [previous_client_state])[-MAX_CLIENT_STATE_HISTORY:]

        try:
            response = self.table.update_item(
                Key={_PK: pk},
                UpdateExpression=(
                    "SET generation = generation + :inc, "
                    "client_state = :client_state, "
                    "client_state_history = :new_history, "
                    "updated_at = :updated_at"
                ),
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":client_state": client_state,
                    ":new_history": new_history,
                    ":updated_at": Decimal(str(current_time)),
                },
                ReturnValues="ALL_NEW",
            )

            updated_item = response["Attributes"]
            # Add user_id to the dict since DynamoDB stores it in PK
            updated_item["user_id"] = user_id
            # Ensure client_state_history is present (for legacy records)
            if "client_state_history" not in updated_item:  # pragma: nocover
                updated_item["client_state_history"] = []
            return UserRecord.model_validate(updated_item)

        except ClientError as e:
            if e.response["Error"]["Code"] in (
                "ResourceNotFoundException",
                "ProvisionedThroughputExceededException",
                "RequestLimitExceeded",
                "InternalServerError",
            ):
                raise ServiceUnavailableError(
                    f"DynamoDB unavailable: {e.response['Error']['Code']}"
                )
            raise

    def get_or_create_user(self, user_id: str, client_state: str = "") -> UserRecord:
        """Get existing user or create new record with generation 0

        Orchestrates user creation, retrieval, and client state management.
        If the user already exists, returns the existing record.
        If client_state differs from stored value, validates against history
        and increments generation number.

        Args:
            user_id: User identifier from OIDC sub claim (stable)
            client_state: X-Client-State header value (urlsafe-base64 + period, max 32 chars)

        Returns:
            UserRecord with current generation number

        Raises:
            InvalidClientStateError: If client state transition is invalid
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        try:
            # Try to create new user
            return self.create_user(user_id, client_state)

        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # User already exists, fetch existing record
                existing_user = self.get_user(user_id)

                # This should never be None after a ConditionalCheckFailedException,
                # but we guard for type safety
                if existing_user is None:
                    raise ServiceUnavailableError("User exists but could not be retrieved")

                # Check if client_state has changed
                if existing_user.client_state != client_state:
                    # Validate client state against history before accepting
                    self.validate_client_state(existing_user, client_state)

                    # Client state changed, increment generation, update client_state,
                    # and add previous state to history
                    return self.update_user_client_state(
                        user_id,
                        client_state,
                        existing_user.client_state,
                        current_history=existing_user.client_state_history,
                    )

                return existing_user
            raise

    def increment_generation(self, user_id: str) -> int:
        """Increment user's generation number atomically

        Uses DynamoDB UpdateExpression with ADD to ensure atomic increment.
        This invalidates all previously issued tokens for the user.

        Args:
            user_id: User identifier from OIDC sub claim (stable)

        Returns:
            New generation number after increment

        Raises:
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        pk = self._user_pk(user_id)
        current_time = time.time()

        try:
            response = self.table.update_item(
                Key={_PK: pk},
                UpdateExpression="SET generation = generation + :inc, updated_at = :updated_at",
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":updated_at": Decimal(str(current_time)),
                },
                ReturnValues="ALL_NEW",
            )

            updated_item = response["Attributes"]
            return updated_item["generation"]

        except ClientError as e:
            if e.response["Error"]["Code"] in (
                "ResourceNotFoundException",
                "ProvisionedThroughputExceededException",
                "RequestLimitExceeded",
                "InternalServerError",
            ):
                raise ServiceUnavailableError(
                    f"DynamoDB unavailable: {e.response['Error']['Code']}"
                )
            raise

    def validate_generation(self, user_id: str, generation: int) -> bool:
        """Verify generation number matches current value

        Used to validate that a token's generation number is still current.
        If the stored generation is higher, the token has been invalidated.

        Args:
            user_id: User identifier from OIDC sub claim (stable)
            generation: Generation number to validate

        Returns:
            True if generation matches current value, False otherwise

        Raises:
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        user = self.get_user(user_id)

        if user is None:
            return False

        return user.generation == generation
