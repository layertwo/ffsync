"""User manager for DynamoDB operations on token server users"""

from datetime import datetime, timezone
from typing import Optional

from botocore.exceptions import ClientError

from src.shared.exceptions import InvalidClientStateError, ServiceUnavailableError
from src.shared.user import UserRecord
from src.shared.utils import float_to_decimal

_PK = "PK"
PK_PREFIX = "USER"


class UserManager:
    """Manages user operations with DynamoDB for the Token Server"""

    def __init__(self, table):
        """Initialize UserManager

        Args:
            table: DynamoDB Table resource
        """
        self.table = table

    def _user_pk(self, uid: int) -> str:
        """Generate partition key for user record

        Args:
            uid: Numeric user identifier

        Returns:
            Partition key string
        """
        return f"{PK_PREFIX}#{uid}"

    def _encode_user_record(self, user_record: UserRecord) -> dict:
        encoded = user_record.to_dict()
        encoded[_PK] = f"{PK_PREFIX}#{user_record.uid}"
        return encoded

    def create_user(self, uid: int, client_state: str = "") -> UserRecord:
        """Create a new user record with generation 0

        Uses conditional write to ensure atomicity. Raises ConditionalCheckFailedException
        if the user already exists.

        Args:
            uid: Numeric user identifier (hash of OIDC sub claim)
            client_state: X-Client-State header value (urlsafe-base64 + period, max 32 chars)

        Returns:
            UserRecord with generation 0 and empty client_state_history

        Raises:
            ClientError: If user already exists (ConditionalCheckFailedException)
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        current_time = datetime.now(tz=timezone.utc)

        try:

            user_record = UserRecord(
                uid=uid,
                generation=0,
                client_state=client_state,
                client_state_history=[],
                created_at=current_time,
                updated_at=current_time,
            )

            self.table.put_item(
                Item=self._encode_user_record(user_record=user_record),
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

    def get_user(self, uid: int) -> Optional[UserRecord]:
        """Get user record from DynamoDB

        Args:
            uid: Numeric user identifier

        Returns:
            UserRecord if found, None otherwise

        Raises:
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        pk = self._user_pk(uid)

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
            return UserRecord.from_dict(item)

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
        self, uid: int, client_state: str, previous_client_state: str
    ) -> UserRecord:
        """Update client state, add previous to history, and increment generation atomically

        Args:
            uid: Numeric user identifier
            client_state: New X-Client-State value
            previous_client_state: Previous X-Client-State value to add to history

        Returns:
            Updated UserRecord with new generation, client_state, and updated history

        Raises:
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        pk = self._user_pk(uid)
        current_time = datetime.now(tz=timezone.utc)

        try:
            response = self.table.update_item(
                Key={_PK: pk},
                UpdateExpression=(
                    "SET generation = generation + :inc, "
                    "client_state = :client_state, "
                    "client_state_history = list_append("
                    "if_not_exists(client_state_history, :empty_list), :prev_state_list), "
                    "updated_at = :updated_at"
                ),
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":client_state": client_state,
                    ":prev_state_list": [previous_client_state],
                    ":empty_list": [],
                    ":updated_at": float_to_decimal(current_time.timestamp()),
                },
                ReturnValues="ALL_NEW",
            )

            updated_item = response["Attributes"]
            # Add uid to the dict since DynamoDB stores it in PK
            updated_item["uid"] = uid
            # Ensure client_state_history is present (for legacy records)
            if "client_state_history" not in updated_item:
                updated_item["client_state_history"] = []
            return UserRecord.from_dict(updated_item)

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

    def get_or_create_user(self, uid: int, client_state: str = "") -> UserRecord:
        """Get existing user or create new record with generation 0

        Orchestrates user creation, retrieval, and client state management.
        If the user already exists, returns the existing record.
        If client_state differs from stored value, validates against history
        and increments generation number.

        Args:
            uid: Numeric user identifier (hash of OIDC sub claim)
            client_state: X-Client-State header value (urlsafe-base64 + period, max 32 chars)

        Returns:
            UserRecord with current generation number

        Raises:
            InvalidClientStateError: If client state transition is invalid
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        try:
            # Try to create new user
            return self.create_user(uid, client_state)

        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # User already exists, fetch existing record
                existing_user = self.get_user(uid)

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
                        uid, client_state, existing_user.client_state
                    )

                return existing_user
            raise

    def increment_generation(self, uid: int) -> int:
        """Increment user's generation number atomically

        Uses DynamoDB UpdateExpression with ADD to ensure atomic increment.
        This invalidates all previously issued tokens for the user.

        Args:
            uid: Numeric user identifier

        Returns:
            New generation number after increment

        Raises:
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        pk = self._user_pk(uid)
        current_time = datetime.now(tz=timezone.utc)

        try:
            response = self.table.update_item(
                Key={_PK: pk},
                UpdateExpression="SET generation = generation + :inc, updated_at = :updated_at",
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":updated_at": float_to_decimal(current_time.timestamp()),
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

    def validate_generation(self, uid: int, generation: int) -> bool:
        """Verify generation number matches current value

        Used to validate that a token's generation number is still current.
        If the stored generation is higher, the token has been invalidated.

        Args:
            uid: Numeric user identifier
            generation: Generation number to validate

        Returns:
            True if generation matches current value, False otherwise

        Raises:
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        user = self.get_user(uid)

        if user is None:
            return False

        return user.generation == generation
