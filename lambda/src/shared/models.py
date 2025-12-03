from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from dataclasses_json import dataclass_json


class ValidationError(Exception):
    """Validation error for invalid input data"""

    pass


@dataclass_json
@dataclass
class BasicStorageObject:
    """Basic Storage Object model"""

    id: str
    payload: str
    modified: float
    sortindex: Optional[int] = None
    ttl: Optional[int] = None


@dataclass_json
@dataclass
class CollectionData:
    """Collection metadata model"""

    name: str
    modified: float
    count: int
    usage: int


@dataclass_json
@dataclass
class BatchResult:
    """Batch operation result model"""

    success: List[str]
    failed: Dict[str, List[str]]
    modified: float


def get_current_timestamp() -> float:
    """Get current timestamp in seconds since epoch with 2 decimal places precision"""
    return round(datetime.now().timestamp(), 2)


def validate_timestamp(timestamp: float) -> bool:
    """
    Validate that a timestamp is a valid float with proper precision.

    Args:
        timestamp: The timestamp to validate (seconds since epoch)

    Returns:
        True if the timestamp is valid, False otherwise
    """
    if not isinstance(timestamp, (int, float)):
        return False

    # Check if timestamp is positive (after epoch)
    if timestamp < 0:
        return False

    # Check if timestamp has at most 2 decimal places
    # Round to 2 decimal places and compare - if they're equal, it has at most 2 decimal places
    rounded = round(timestamp, 2)
    if abs(timestamp - rounded) > 1e-10:  # Small epsilon for floating point comparison
        return False

    return True
