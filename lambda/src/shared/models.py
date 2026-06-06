"""Shared Pydantic models.

Wire-shape models live in `src.shared.generated.*` and are produced from the
smithy IDL via `lambda/scripts/codegen.sh`. This module re-exports them under
their public names. Storage-layer code (storage_manager) uses the same
generated classes; DynamoDB serialization is handled by the `to_dynamo_dict`
helper, which converts float fields to Decimal at the boto3 boundary.
"""

import re
import time
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from src.shared.generated.auth_models import AccountCreateRequestContent as AccountCreateInput
from src.shared.generated.auth_models import AccountCreateResponseContent as AccountCreateOutput
from src.shared.generated.auth_models import AccountKeysResponseContent as AccountKeysOutput
from src.shared.generated.auth_models import AccountLoginRequestContent as AccountLoginInput
from src.shared.generated.auth_models import AccountLoginResponseContent as AccountLoginOutput
from src.shared.generated.auth_models import AccountStatusResponseContent as AccountStatusOutput
from src.shared.generated.auth_models import AttachedClient as _WireAttachedClient
from src.shared.generated.auth_models import DeviceRecord as DeviceOutput
from src.shared.generated.auth_models import (
    OAuthAuthorizationRequestContent as OAuthAuthorizationInput,
)
from src.shared.generated.auth_models import (
    OAuthAuthorizationResponseContent as OAuthAuthorizationOutput,
)
from src.shared.generated.auth_models import OAuthDestroyRequestContent as OAuthDestroyInput
from src.shared.generated.auth_models import OAuthTokenRequestContent as OAuthTokenInput
from src.shared.generated.auth_models import OAuthTokenResponseContent as _WireOAuthTokenOutput
from src.shared.generated.auth_models import OIDCCodeExchangeRequestContent as OIDCExchangeInput
from src.shared.generated.auth_models import OIDCCodeExchangeResponseContent as OIDCExchangeOutput
from src.shared.generated.auth_models import RegisterDeviceRequestContent as DeviceInput
from src.shared.generated.auth_models import (
    ScopedKeyDataEntry,
)
from src.shared.generated.auth_models import ScopedKeyDataRequestContent as ScopedKeyDataInput
from src.shared.generated.auth_models import SessionStatusResponseContent as SessionStatusOutput
from src.shared.generated.profile_models import GetProfileResponseContent as _WireProfileOutput
from src.shared.generated.storage_models import BasicStorageObject
from src.shared.generated.storage_models import BasicStorageObject as BSOOutput
from src.shared.generated.storage_models import BasicStorageObjectInput as BSOInput
from src.shared.generated.storage_models import BatchResult
from src.shared.generated.storage_models import BatchResult as BatchResultOutput
from src.shared.generated.storage_models import CollectionData
from src.shared.generated.storage_models import CollectionData as CollectionDataOutput
from src.shared.generated.storage_models import (
    GetConfigurationInfoResponseContent as ConfigurationOutput,
)
from src.shared.generated.storage_models import (
    ListCollectionsResponseContent as CollectionsResponse,
)
from src.shared.generated.token_models import GetTokenResponseContent as TokenOutput

# ---------------------------------------------------------------------------
# DynamoDB serialization helpers
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    """Validation error for invalid input data"""


def to_dynamo_dict(model: BaseModel) -> dict:
    """Convert a pydantic model to a DynamoDB-compatible dict.

    boto3's DynamoDB client rejects Python floats (`TypeError: Float types
    are not supported`). Convert every float field to Decimal via str() to
    preserve the exact value. Ints, strs, bools, lists, dicts pass through
    unchanged.
    """
    return {k: _to_dynamo(v) for k, v in model.model_dump().items()}


def _to_dynamo(v):
    if isinstance(v, float):
        return Decimal(str(v))
    if isinstance(v, dict):
        return {k: _to_dynamo(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_to_dynamo(x) for x in v]
    return v


def bso_to_item(
    bso: BasicStorageObject,
    user_id: str,
    collection_name: str,
    ttl: int | None = None,
) -> dict:
    """Build a DynamoDB item dict for a BSO with PK/SK and optional TTL expiry.

    `ttl` is a DynamoDB-only concept (write-time per Mozilla spec) and isn't
    part of the BSO wire shape. Callers pass it explicitly; it's translated
    into an absolute `expiry` timestamp on the stored item.
    """
    item = to_dynamo_dict(bso)
    item["PK"] = f"USER#{user_id}#COLLECTION#{collection_name}"
    item["SK"] = f"OBJECT#{bso.id}"
    if ttl is not None:
        item["expiry"] = int(time.time()) + ttl
    return item


def collection_to_item(collection: CollectionData, user_id: str) -> dict:
    """Build a DynamoDB item dict for collection metadata with PK/SK + GSI key."""
    item = to_dynamo_dict(collection)
    item["PK"] = f"USER#{user_id}#COLLECTION#{collection.name}"
    item["SK"] = "METADATA"
    item["user_id"] = user_id
    return item


# ---------------------------------------------------------------------------
# Wire augmentations — generated model + project-specific defaults
# smithy-openapi drops `@default` traits during conversion, so defaults from
# the IDL (e.g. token_type = "bearer") don't survive into the generated models.
# Restore them via subclass until smithy-openapi grows a fix.
# ---------------------------------------------------------------------------


class OAuthTokenOutput(_WireOAuthTokenOutput):
    token_type: str = "bearer"


class ProfileOutput(_WireProfileOutput):
    locale: str = "en-US"


class AttachedClientOutput(_WireAttachedClient):
    location: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Wire models still hand-written (divergent from smithy — fixes queued)
# ---------------------------------------------------------------------------


# TODO(smithy, tier 2): replace with per-operation Delete*ResponseContent types
# from generated/storage_models.py (DeleteCollectionResponseContent etc.).
class ModifiedOutput(BaseModel):
    modified: float


# ---------------------------------------------------------------------------
# TypeAdapters for list serialization
# ---------------------------------------------------------------------------


BSOListAdapter = TypeAdapter(list[BSOOutput])
DeviceListAdapter = TypeAdapter(list[DeviceOutput])
ClientListAdapter = TypeAdapter(list[AttachedClientOutput])


# ---------------------------------------------------------------------------
# Helpers and validation
# ---------------------------------------------------------------------------


def get_current_timestamp() -> float:
    """Current timestamp in seconds since epoch, rounded to 2 decimals."""
    return round(time.time(), 2)


MAX_PAYLOAD_BYTES = 256 * 1024  # 256 KB
MAX_SORTINDEX_DIGITS = 9
MAX_TTL_DIGITS = 9
MAX_SORTINDEX = 10**MAX_SORTINDEX_DIGITS - 1
MIN_SORTINDEX = -(10**MAX_SORTINDEX_DIGITS - 1)
MAX_TTL = 10**MAX_TTL_DIGITS - 1

# Path-parameter validators delegate to typed adapters whose constraints
# mirror the smithy CollectionName / ObjectId shapes. Keep the constants
# exported (tests reference them) but derive runtime checks from the adapter
# so changes to the smithy spec only need to be reflected in one place.
MAX_COLLECTION_NAME_LENGTH = 32
MAX_BSO_ID_LENGTH = 64

CollectionName = Annotated[
    str,
    StringConstraints(pattern=r"^[a-zA-Z0-9._-]+$", min_length=1, max_length=32),
]
ObjectId = Annotated[
    str,
    StringConstraints(pattern=r"^[\x20-\x7E]+$", min_length=1, max_length=64),
]
_CollectionNameAdapter = TypeAdapter(CollectionName)
_ObjectIdAdapter = TypeAdapter(ObjectId)
_VALID_COLLECTION_CHAR_RE = re.compile(r"[a-zA-Z0-9._-]")


def validate_payload_size(payload: str) -> None:
    payload_bytes = len(payload.encode("utf-8"))
    if payload_bytes > MAX_PAYLOAD_BYTES:
        raise ValidationError(
            f"Payload size {payload_bytes} bytes exceeds maximum {MAX_PAYLOAD_BYTES} bytes"
        )


def validate_bso_id(bso_id: str) -> None:
    try:
        _ObjectIdAdapter.validate_python(bso_id)
    except PydanticValidationError:
        if len(bso_id) > MAX_BSO_ID_LENGTH:
            raise ValidationError(
                f"BSO ID length {len(bso_id)} exceeds maximum {MAX_BSO_ID_LENGTH} characters"
            )
        for char in bso_id:
            if ord(char) < 0x20 or ord(char) > 0x7E:
                raise ValidationError(
                    f"BSO ID contains non-printable ASCII character: {repr(char)}"
                )
        raise ValidationError(f"Invalid BSO ID: {bso_id!r}")


def validate_collection_name(collection_name: str) -> None:
    try:
        _CollectionNameAdapter.validate_python(collection_name)
    except PydanticValidationError:
        if len(collection_name) > MAX_COLLECTION_NAME_LENGTH:
            raise ValidationError(
                f"Collection name length {len(collection_name)} exceeds maximum "
                f"{MAX_COLLECTION_NAME_LENGTH} characters"
            )
        for char in collection_name:
            if not _VALID_COLLECTION_CHAR_RE.match(char):
                raise ValidationError(
                    f"Collection name contains invalid character: {repr(char)}. "
                    f"Only alphanumeric, underscore, hyphen, and period are allowed."
                )
        raise ValidationError(f"Invalid collection name: {collection_name!r}")
