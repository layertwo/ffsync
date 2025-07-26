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
    modified: int
    sortindex: Optional[int] = None
    ttl: Optional[int] = None


@dataclass_json
@dataclass
class CollectionData:
    """Collection metadata model"""

    name: str
    modified: int
    count: int
    usage: int


@dataclass_json
@dataclass
class BatchResult:
    """Batch operation result model"""

    success: List[str]
    failed: Dict[str, List[str]]
    modified: int


def get_current_timestamp() -> int:
    """Get current timestamp in milliseconds since epoch"""
    return int(datetime.now().timestamp() * 1000)
