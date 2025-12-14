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
