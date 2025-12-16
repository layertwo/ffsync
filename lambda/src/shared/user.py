"""User record data model"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from dataclasses_json import DataClassJsonMixin, config

from src.shared.utils import datetime_decoder, datetime_encoder


@dataclass
class UserRecord(DataClassJsonMixin):
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
    created_at: datetime = field(
        metadata=config(encoder=datetime_encoder, decoder=datetime_decoder)
    )
    updated_at: datetime = field(
        metadata=config(encoder=datetime_encoder, decoder=datetime_decoder)
    )
    client_state_history: List[str] = field(default_factory=list)
