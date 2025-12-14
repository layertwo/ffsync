import json
from datetime import datetime, timezone
from decimal import Decimal


def datetime_encoder(dt: datetime) -> Decimal:
    """Convert datetime to Unix timestamp (Decimal) for DynamoDB serialization"""
    # Treat naive datetime as UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # pragma: nocover
    return Decimal(str(dt.timestamp()))


def datetime_decoder(timestamp: float) -> datetime:
    """Convert Unix timestamp (float/Decimal) to datetime for deserialization"""
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)


def float_to_decimal(value: float) -> Decimal:
    """Convert float to Decimal for DynamoDB serialization"""
    return Decimal(str(value))


def decimal_to_float(value: Decimal) -> float:
    """Convert Decimal to float for deserialization"""
    return float(value)


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal objects by converting them to float"""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def json_dumps(obj, **kwargs) -> str:
    """JSON dumps wrapper that handles Decimal objects"""
    return json.dumps(obj, cls=DecimalEncoder, **kwargs)
