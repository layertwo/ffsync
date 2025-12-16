from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dataclasses_json import DataClassJsonMixin, config

from src.shared.utils import datetime_decoder, datetime_encoder


class ValidationError(Exception):
    """Validation error for invalid input data"""

    pass


@dataclass
class BasicStorageObject(DataClassJsonMixin):
    """Basic Storage Object model"""

    id: str
    payload: str
    modified: datetime = field(metadata=config(encoder=datetime_encoder, decoder=datetime_decoder))
    sortindex: Optional[int] = None
    ttl: Optional[int] = None


@dataclass
class CollectionData(DataClassJsonMixin):
    """Collection metadata model"""

    name: str
    modified: datetime = field(metadata=config(encoder=datetime_encoder, decoder=datetime_decoder))
    count: int
    usage: int


@dataclass
class BatchResult(DataClassJsonMixin):
    """Batch operation result model"""

    success: List[str]
    failed: Dict[str, List[str]]
    modified: datetime = field(metadata=config(encoder=datetime_encoder, decoder=datetime_decoder))


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


def validate_sortindex(sortindex: Optional[int]) -> None:
    """
    Validate BSO sortindex.

    Args:
        sortindex: The BSO sortindex value

    Raises:
        ValidationError: If sortindex is not an integer or exceeds 9 digits
    """
    if sortindex is None:
        return

    if not isinstance(sortindex, int):
        raise ValidationError(f"Sortindex must be an integer, got {type(sortindex).__name__}")

    if sortindex > MAX_SORTINDEX or sortindex < MIN_SORTINDEX:
        raise ValidationError(
            f"Sortindex {sortindex} exceeds maximum 9 digits (range: {MIN_SORTINDEX} to {MAX_SORTINDEX})"
        )


def validate_ttl(ttl: Optional[int]) -> None:
    """
    Validate BSO TTL (Time-To-Live).

    Args:
        ttl: The BSO TTL value in seconds

    Raises:
        ValidationError: If TTL is not a positive integer or exceeds 9 digits
    """
    if ttl is None:
        return

    if not isinstance(ttl, int):
        raise ValidationError(f"TTL must be an integer, got {type(ttl).__name__}")

    if ttl <= 0:
        raise ValidationError(f"TTL must be a positive integer, got {ttl}")

    if ttl > MAX_TTL:
        raise ValidationError(f"TTL {ttl} exceeds maximum 9 digits (max: {MAX_TTL})")


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

    # urlsafe-base64 alphabet: a-z, A-Z, 0-9, underscore, hyphen, plus period
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")

    for char in collection_name:
        if char not in allowed_chars:
            raise ValidationError(
                f"Collection name contains invalid character: {repr(char)}. "
                f"Only alphanumeric, underscore, hyphen, and period are allowed."
            )
