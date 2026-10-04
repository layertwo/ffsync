"""Device management for FxA device registration and listing."""

import re
import time
import uuid
from typing import TYPE_CHECKING, Any, Optional, cast

from boto3.dynamodb.conditions import Attr

if TYPE_CHECKING:
    from types_boto3_dynamodb.service_resource import Table

DEVICE_PREFIX = "DEVICE"
_HAWK_ID_PATTERN = re.compile(r'id="([^"]+)"')


class DeviceManager:
    """Manages FxA device records in DynamoDB."""

    def __init__(self, table: "Table"):
        self.table = table

    def _device_pk(self, uid: str, device_id: str) -> str:
        return f"{DEVICE_PREFIX}#{uid}#{device_id}"

    def upsert_device(self, uid: str, session_token_id: str, data: dict) -> dict:
        """Create or update a device record."""
        now = int(time.time() * 1000)
        device_id = data.get("id")

        if device_id:
            # Update: get existing, merge new fields
            response = self.table.get_item(Key={"PK": self._device_pk(uid, device_id)})
            existing = response.get("Item", {})
            existing.pop("PK", None)
            # Merge: new data overwrites existing, but preserve createdAt
            device = {**existing, **{k: v for k, v in data.items() if v is not None}}
            device["lastAccessTime"] = now
            device["sessionTokenId"] = session_token_id
        else:
            # Create new device
            device_id = uuid.uuid4().hex
            device = {
                "id": device_id,
                "name": data.get("name", ""),
                "type": data.get("type", "desktop"),
                "pushCallback": data.get("pushCallback"),
                "pushPublicKey": data.get("pushPublicKey"),
                "pushAuthKey": data.get("pushAuthKey"),
                "pushEndpointExpired": False,
                "availableCommands": data.get("availableCommands", {}),
                "sessionTokenId": session_token_id,
                "createdAt": now,
                "lastAccessTime": now,
            }

        self.table.put_item(Item={"PK": self._device_pk(uid, device_id), **device})
        return device

    def get_devices(self, uid: str, filter_idle_timestamp: Optional[int] = None) -> list[dict]:
        """List all devices for a user.

        Scans because the auth table has no GSI. DynamoDB caps each page at 1 MB *scanned*
        (before FilterExpression is applied), so a page can come back empty while more devices
        remain — pagination must follow LastEvaluatedKey rather than stop on an empty page.
        """
        devices = []
        scan_kwargs: dict[str, Any] = {
            "FilterExpression": Attr("PK").begins_with(f"{DEVICE_PREFIX}#{uid}#")
        }

        while True:
            response = self.table.scan(**scan_kwargs)
            for item in cast(list[dict[str, Any]], response.get("Items", [])):
                item.pop("PK", None)
                if filter_idle_timestamp and item.get("lastAccessTime", 0) < filter_idle_timestamp:
                    continue
                devices.append(item)

            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return devices
            scan_kwargs["ExclusiveStartKey"] = last_key
