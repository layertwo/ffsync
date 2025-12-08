"""User record data model"""

from dataclasses import dataclass

from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class UserRecord:
    """
    User record stored in DynamoDB

    Attributes:
        user_id: Unique identifier from OIDC sub claim
        generation: Monotonic counter for token invalidation
        created_at: Unix timestamp when user was created
        updated_at: Unix timestamp when user was last updated
    """

    user_id: str
    generation: int
    created_at: float
    updated_at: float
