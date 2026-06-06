"""User record data model."""

from pydantic import BaseModel

from src.shared.models import to_dynamo_dict


class UserRecord(BaseModel):
    """
    User record stored in DynamoDB.

    Attributes:
        user_id: User identifier from OIDC sub claim (stable, used as PK)
        generation: Monotonic counter for token invalidation
        client_state: X-Client-State header value (urlsafe-base64 + period, max 32 chars)
        created_at: Seconds since epoch (float, microsecond precision)
        updated_at: Seconds since epoch (float, microsecond precision)
        client_state_history: List of previously-seen X-Client-State values

    Note: uid is NOT stored - it's derived on-demand as hash(user_id + generation)
    """

    user_id: str
    generation: int
    client_state: str
    created_at: float
    updated_at: float
    client_state_history: list[str] = []

    def to_item(self) -> dict:
        """Produce a complete DynamoDB item with PK."""
        item = to_dynamo_dict(self)
        item["PK"] = f"USER#{self.user_id}"
        return item
