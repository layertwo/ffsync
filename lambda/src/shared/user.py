"""User record data model"""

from dataclasses import dataclass, field
from datetime import datetime

from dataclasses_json import DataClassJsonMixin, config

from src.shared.utils import datetime_decoder, datetime_encoder


@dataclass
class UserRecord(DataClassJsonMixin):
    """
    User record stored in DynamoDB

    Attributes:
        user_id: Unique identifier from OIDC sub claim
        generation: Monotonic counter for token invalidation
        client_state: X-Client-State header value (hex string, max 32 chars)
        created_at: Datetime when user was created
        updated_at: Datetime when user was last updated
    """

    user_id: str
    generation: int
    client_state: str
    created_at: datetime = field(
        metadata=config(encoder=datetime_encoder, decoder=datetime_decoder)
    )
    updated_at: datetime = field(
        metadata=config(encoder=datetime_encoder, decoder=datetime_decoder)
    )
