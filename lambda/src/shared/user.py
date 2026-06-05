"""User record data model"""

from datetime import datetime
from typing import List

from src.shared.models import DynamoModel


class UserRecord(DynamoModel):
    """
    User record stored in DynamoDB

    Attributes:
        user_id: User identifier from OIDC sub claim (stable, used as PK)
        generation: Monotonic counter for token invalidation
        client_state: X-Client-State header value (urlsafe-base64 + period, max 32 chars)
        created_at: Datetime when user was created
        updated_at: Datetime when user was last updated
        client_state_history: List of previously-seen X-Client-State values

    Note: uid is NOT stored - it's derived on-demand as hash(user_id + generation)
    """

    user_id: str
    generation: int
    client_state: str
    created_at: datetime
    updated_at: datetime
    client_state_history: List[str] = []

    def to_item(self) -> dict:
        """Produce a complete DynamoDB item with PK."""
        item = self._to_dynamodb_dict()
        item["PK"] = f"USER#{self.user_id}"
        return item
