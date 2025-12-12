"""User manager for DynamoDB operations on token server users"""

from decimal import Decimal
from typing import Optional

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from src.shared.exceptions import ServiceUnavailableError
from src.shared.models import get_current_timestamp
from src.shared.user import UserRecord


class UserManager:
    """Manages user operations with DynamoDB for the Token Server"""

    def __init__(self, table):
        """Initialize UserManager

        Args:
            table: DynamoDB Table resource (low-level client)
        """
        self.table = table
        self._serializer = TypeSerializer()
        self._deserializer = TypeDeserializer()

    def _user_pk(self, user_id: str) -> str:
        """Generate partition key for user record

        Args:
            user_id: User identifier from OIDC sub claim

        Returns:
            Partition key string
        """
        return f"USER#{user_id}"

    def _deserialize_item(self, item: dict) -> dict:
        """Convert DynamoDB item to Python dict

        Args:
            item: DynamoDB item with type descriptors

        Returns:
            Python dict with native types
        """
        return {k: self._deserializer.deserialize(v) for k, v in item.items()}

    def _serialize_item(self, data: dict) -> dict:
        """Convert Python dict to DynamoDB item format, skipping None values

        Args:
            data: Python dict with native types

        Returns:
            DynamoDB item with type descriptors
        """
        return {k: self._serializer.serialize(v) for k, v in data.items() if v is not None}

    def create_user(self, user_id: str, client_state: str = "") -> UserRecord:
        """Create a new user record with generation 0

        Uses conditional write to ensure atomicity. Raises ConditionalCheckFailedException
        if the user already exists.

        Args:
            user_id: Unique user identifier from OIDC sub claim
            client_state: X-Client-State header value (hex string, max 32 chars)

        Returns:
            UserRecord with generation 0

        Raises:
            ClientError: If user already exists (ConditionalCheckFailedException)
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        pk = self._user_pk(user_id)
        current_time = get_current_timestamp()

        try:
            user_data = {
                "PK": pk,
                "user_id": user_id,
                "generation": 0,
                "client_state": client_state,
                "created_at": Decimal(str(current_time)),
                "updated_at": Decimal(str(current_time)),
            }
            user_item = self._serialize_item(user_data)

            self.table.put_item(
                Item=user_item,
                ConditionExpression="attribute_not_exists(PK)",
            )

            return UserRecord(
                user_id=user_id,
                generation=0,
                client_state=client_state,
                created_at=current_time,
                updated_at=current_time,
            )

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
            user_id: User identifier

        Returns:
            UserRecord if found, None otherwise

        Raises:
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        pk = self._user_pk(user_id)

        try:
            response = self.table.get_item(
                Key={"PK": {"S": pk}},
            )

            if "Item" not in response:
                return None

            item = self._deserialize_item(response["Item"])
            return UserRecord(
                user_id=item["user_id"],
                generation=(
                    int(item["generation"])
                    if isinstance(item["generation"], Decimal)
                    else item["generation"]
                ),
                client_state=item.get("client_state", ""),
                created_at=(
                    float(item["created_at"])
                    if isinstance(item["created_at"], Decimal)
                    else item["created_at"]
                ),
                updated_at=(
                    float(item["updated_at"])
                    if isinstance(item["updated_at"], Decimal)
                    else item["updated_at"]
                ),
            )

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

    def update_user_client_state(self, user_id: str, client_state: str) -> UserRecord:
        """Update client state and increment generation atomically

        Args:
            user_id: User identifier
            client_state: New X-Client-State value

        Returns:
            Updated UserRecord with new generation and client_state

        Raises:
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        pk = self._user_pk(user_id)
        current_time = get_current_timestamp()

        try:
            response = self.table.update_item(
                Key={"PK": {"S": pk}},
                UpdateExpression=(
                    "SET generation = generation + :inc, "
                    "client_state = :client_state, "
                    "updated_at = :updated_at"
                ),
                ExpressionAttributeValues={
                    ":inc": {"N": "1"},
                    ":client_state": {"S": client_state},
                    ":updated_at": {"N": str(current_time)},
                },
                ReturnValues="ALL_NEW",
            )

            updated_item = self._deserialize_item(response["Attributes"])
            generation = updated_item["generation"]

            return UserRecord(
                user_id=user_id,
                generation=int(generation) if isinstance(generation, Decimal) else generation,
                client_state=updated_item["client_state"],
                created_at=(
                    float(updated_item["created_at"])
                    if isinstance(updated_item["created_at"], Decimal)
                    else updated_item["created_at"]
                ),
                updated_at=(
                    float(updated_item["updated_at"])
                    if isinstance(updated_item["updated_at"], Decimal)
                    else updated_item["updated_at"]
                ),
            )

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
        If client_state differs from stored value, increments generation number.

        Args:
            user_id: Unique user identifier from OIDC sub claim
            client_state: X-Client-State header value (hex string, max 32 chars)

        Returns:
            UserRecord with current generation number

        Raises:
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
                    # Client state changed, increment generation and update client_state
                    return self.update_user_client_state(user_id, client_state)

                return existing_user
            raise

    def increment_generation(self, user_id: str) -> int:
        """Increment user's generation number atomically

        Uses DynamoDB UpdateExpression with ADD to ensure atomic increment.
        This invalidates all previously issued tokens for the user.

        Args:
            user_id: User identifier

        Returns:
            New generation number after increment

        Raises:
            ServiceUnavailableError: If DynamoDB is unavailable
        """
        pk = self._user_pk(user_id)
        current_time = get_current_timestamp()

        try:
            response = self.table.update_item(
                Key={"PK": {"S": pk}},
                UpdateExpression="SET generation = generation + :inc, updated_at = :updated_at",
                ExpressionAttributeValues={
                    ":inc": {"N": "1"},
                    ":updated_at": {"N": str(current_time)},
                },
                ReturnValues="ALL_NEW",
            )

            updated_item = self._deserialize_item(response["Attributes"])
            generation = updated_item["generation"]
            return int(generation) if isinstance(generation, Decimal) else generation

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
            user_id: User identifier
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
