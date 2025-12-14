"""Token response data model"""

from dataclasses import dataclass

from dataclasses_json import DataClassJsonMixin


@dataclass
class TokenResponse(DataClassJsonMixin):
    """
    Token response returned to Firefox Sync clients

    Attributes:
        id: HAWK identifier (base64-encoded)
        key: HAWK shared secret (hex-encoded)
        api_endpoint: Full storage API URL
        uid: Numeric user ID (hash of user_id)
        duration: Token validity in seconds (300)
        hashalg: Hash algorithm for HAWK ("sha256")
    """

    id: str
    key: str
    api_endpoint: str
    uid: int
    duration: int
    hashalg: str
