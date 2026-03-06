from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from pydantic.alias_generators import to_camel


class ValidationError(Exception):
    """Validation error for invalid input data"""

    pass


class DynamoModel(BaseModel):
    """Base for models stored in DynamoDB.

    Handles:
    - Decimal/float → datetime coercion on read  (model_validator)
    - datetime → Decimal serialization on write  (model_dump override)
    - float → Decimal conversion for all numeric fields
    """

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _coerce_timestamps(cls, data):
        """Coerce Decimal/float values to datetime for annotated datetime fields."""
        if not isinstance(data, dict):
            return data
        for field_name, field_info in cls.model_fields.items():
            if field_info.annotation is datetime and field_name in data:
                v = data[field_name]
                if not isinstance(v, datetime):
                    data[field_name] = datetime.fromtimestamp(float(v), tz=timezone.utc)
        return data

    def _to_dynamodb_dict(self) -> dict:
        """Serialize to a DynamoDB-compatible dict (datetime/float → Decimal)."""
        data = super().model_dump()
        for k, v in data.items():
            if isinstance(v, datetime):
                data[k] = Decimal(str(v.timestamp()))
            elif isinstance(v, float):
                data[k] = Decimal(str(v))
        return data


class BasicStorageObject(DynamoModel):
    """Basic Storage Object — internal model for StorageManager ↔ DynamoDB."""

    id: str
    payload: str = ""
    modified: datetime
    sortindex: Optional[int] = None
    ttl: Optional[int] = None

    def to_item(self, user_id: str, collection_name: str) -> dict:
        """Produce a complete DynamoDB item with PK/SK and optional TTL expiry."""
        item = self._to_dynamodb_dict()
        item["PK"] = f"USER#{user_id}#COLLECTION#{collection_name}"
        item["SK"] = f"OBJECT#{self.id}"
        if self.ttl is not None:
            item["expiry"] = int(datetime.now(tz=timezone.utc).timestamp()) + self.ttl
        return item


class CollectionData(DynamoModel):
    """Collection metadata — internal model for StorageManager ↔ DynamoDB."""

    name: str
    modified: datetime
    count: int = 0
    usage: int = 0

    def to_item(self, user_id: str) -> dict:
        """Produce a complete DynamoDB item with PK/SK and GSI key."""
        item = self._to_dynamodb_dict()
        item["PK"] = f"USER#{user_id}#COLLECTION#{self.name}"
        item["SK"] = "METADATA"
        item["user_id"] = user_id
        return item


class BatchResult(BaseModel):
    """Batch operation result."""

    success: List[str]
    failed: Dict[str, List[str]]
    modified: datetime


def get_current_timestamp() -> float:
    """Get current timestamp in seconds since epoch with 2 decimal places precision"""
    return round(datetime.now(tz=timezone.utc).timestamp(), 2)


# Validation constants
MAX_PAYLOAD_BYTES = 256 * 1024  # 256 KB
MAX_SORTINDEX_DIGITS = 9
MAX_TTL_DIGITS = 9
MAX_SORTINDEX = 10**MAX_SORTINDEX_DIGITS - 1  # 999999999
MIN_SORTINDEX = -(10**MAX_SORTINDEX_DIGITS - 1)  # -999999999
MAX_TTL = 10**MAX_TTL_DIGITS - 1  # 999999999
MAX_COLLECTION_NAME_LENGTH = 32
MAX_BSO_ID_LENGTH = 64
_ALLOWED_COLLECTION_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-."
)


def validate_payload_size(payload: str) -> None:
    """
    Validate BSO payload size.

    Args:
        payload: The BSO payload string

    Raises:
        ValidationError: If payload exceeds MAX_PAYLOAD_BYTES (256 KB)
    """
    payload_bytes = len(payload.encode("utf-8"))
    if payload_bytes > MAX_PAYLOAD_BYTES:
        raise ValidationError(
            f"Payload size {payload_bytes} bytes exceeds maximum {MAX_PAYLOAD_BYTES} bytes"
        )


def validate_bso_id(bso_id: str) -> None:
    """
    Validate BSO ID.

    Args:
        bso_id: The BSO ID string

    Raises:
        ValidationError: If ID exceeds 64 characters or contains non-printable ASCII
    """
    if len(bso_id) > MAX_BSO_ID_LENGTH:
        raise ValidationError(
            f"BSO ID length {len(bso_id)} exceeds maximum {MAX_BSO_ID_LENGTH} characters"
        )

    # Check for printable ASCII (0x20-0x7E)
    for char in bso_id:
        if ord(char) < 0x20 or ord(char) > 0x7E:
            raise ValidationError(f"BSO ID contains non-printable ASCII character: {repr(char)}")


def validate_collection_name(collection_name: str) -> None:
    """
    Validate collection name.

    Collection names must:
    - Be at most 32 characters
    - Contain only urlsafe-base64 alphabet (alphanumeric, underscore, hyphen) and period

    Args:
        collection_name: The collection name string

    Raises:
        ValidationError: If collection name is invalid
    """
    if len(collection_name) > MAX_COLLECTION_NAME_LENGTH:
        raise ValidationError(
            f"Collection name length {len(collection_name)} exceeds maximum {MAX_COLLECTION_NAME_LENGTH} characters"
        )

    for char in collection_name:
        if char not in _ALLOWED_COLLECTION_CHARS:
            raise ValidationError(
                f"Collection name contains invalid character: {repr(char)}. "
                f"Only alphanumeric, underscore, hyphen, and period are allowed."
            )


# ---------------------------------------------------------------------------
# Pydantic v2 models (new — coexist with dataclass models above)
# ---------------------------------------------------------------------------


class CamelModel(BaseModel):
    """Base for FxA API models - camelCase on the wire, snake_case internally."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


# --- Storage models (snake_case per Mozilla SyncStorage spec) ---


class BSOOutput(BaseModel):
    id: str
    payload: str
    modified: float
    sortindex: Optional[int] = None

    @classmethod
    def from_bso(cls, bso: "BasicStorageObject") -> "BSOOutput":
        return cls(
            id=bso.id,
            payload=bso.payload,
            modified=round(bso.modified.timestamp(), 2),
            sortindex=bso.sortindex,
        )


class BSOInput(BaseModel):
    id: Optional[str] = None
    payload: Optional[str] = None
    sortindex: Optional[int] = Field(default=None, ge=-999999999, le=999999999)
    ttl: Optional[int] = Field(default=None, gt=0, le=999999999)


class BatchResultOutput(BaseModel):
    success: list[str]
    failed: dict[str, list[str]]
    modified: float


class CollectionDataOutput(BaseModel):
    name: str
    modified: float
    count: int
    usage: int


class ModifiedOutput(BaseModel):
    modified: float


class CollectionsResponse(BaseModel):
    collections: list[CollectionDataOutput]


BSOListAdapter = TypeAdapter(list[BSOOutput])


# --- Device / Auth models (camelCase on the wire) ---


class DeviceInput(CamelModel):
    id: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    push_callback: Optional[str] = None
    push_public_key: Optional[str] = None
    push_auth_key: Optional[str] = None
    available_commands: Optional[dict] = None


class DeviceOutput(CamelModel):
    id: str
    name: Optional[str] = None
    type: Optional[str] = None
    push_callback: Optional[str] = None
    push_public_key: Optional[str] = None
    push_auth_key: Optional[str] = None
    push_endpoint_expired: bool = False
    available_commands: dict = {}
    session_token_id: Optional[str] = None
    is_current_device: bool = False
    created_at: Optional[int] = None
    last_access_time: Optional[int] = None


DeviceListAdapter = TypeAdapter(list[DeviceOutput])


class AttachedClientOutput(CamelModel):
    client_id: Optional[str] = None
    device_id: Optional[str] = None
    session_token_id: Optional[str] = None
    refresh_token_id: Optional[str] = None
    is_current_session: bool = False
    device_type: Optional[str] = None
    name: Optional[str] = None
    created_time: Optional[int] = None
    last_access_time: Optional[int] = None
    scope: Optional[list[str]] = None
    location: dict = {}
    user_agent: Optional[str] = None
    os: Optional[str] = None


ClientListAdapter = TypeAdapter(list[AttachedClientOutput])


class AccountCreateInput(CamelModel):
    email: str
    auth_pw: str = Field(min_length=64, max_length=64)


class AccountCreateOutput(CamelModel):
    uid: str
    session_token: str
    key_fetch_token: str
    verified: bool


class AccountLoginInput(CamelModel):
    email: str
    auth_pw: str = Field(min_length=64, max_length=64)


class AccountLoginOutput(CamelModel):
    uid: str
    session_token: str
    key_fetch_token: Optional[str] = None
    verified: bool


class AccountStatusOutput(BaseModel):
    exists: bool


class AccountKeysOutput(BaseModel):
    bundle: str


class SessionStatusOutput(BaseModel):
    state: str
    uid: str


class ScopedKeyDataInput(BaseModel):
    scope: str


class ScopedKeyDataEntry(CamelModel):
    identifier: str
    key_rotation_secret: str
    key_rotation_timestamp: int


class OAuthAuthorizationInput(CamelModel):
    client_id: str
    scope: str
    state: str
    redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob"
    code_challenge: Optional[str] = None
    code_challenge_method: str = "S256"
    keys_jwe: Optional[str] = None


class OAuthAuthorizationOutput(BaseModel):
    code: str
    state: str
    redirect: str


class OAuthTokenInput(CamelModel):
    grant_type: str
    code: Optional[str] = None
    code_verifier: Optional[str] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    client_id: Optional[str] = None
    ttl: Optional[int] = None


class OAuthTokenOutput(CamelModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    scope: str
    refresh_token: Optional[str] = None
    auth_at: int
    keys_jwe: Optional[str] = None


class OAuthDestroyInput(BaseModel):
    token: str


class OIDCExchangeInput(CamelModel):
    code: str
    code_verifier: str
    redirect_uri: str


class OIDCExchangeOutput(CamelModel):
    email: str
    access_token: str
    account_exists: bool


class TokenOutput(BaseModel):
    id: str
    key: str
    api_endpoint: str
    uid: int
    duration: int
    hashalg: str


class ProfileOutput(CamelModel):
    uid: str
    email: str
    locale: str = "en-US"
    avatar: str
    avatar_default: bool
    sub: str


class ConfigurationOutput(BaseModel):
    max_request_bytes: int
    max_post_records: int
    max_post_bytes: int
    max_record_payload_bytes: int
    max_total_records: Optional[int] = None
    max_total_bytes: Optional[int] = None
