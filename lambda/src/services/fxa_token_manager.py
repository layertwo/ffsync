"""FxA Token Manager for session tokens and key-fetch tokens in DynamoDB"""

import base64
import hashlib
import hmac
import re
import time
from typing import Optional

from botocore.exceptions import ClientError

from src.services import fxa_crypto

_PK = "PK"
SESSION_TOKEN_INFO = "identity.mozilla.com/picl/v1/sessionToken"
KEY_FETCH_TOKEN_INFO = "identity.mozilla.com/picl/v1/keyFetchToken"

SESSION_PREFIX = "SESSION"
KEYFETCH_PREFIX = "KEYFETCH"

HAWK_HEADER_PATTERN = re.compile(
    r'id="(?P<id>[^"]+)".*ts="(?P<ts>[^"]+)".*nonce="(?P<nonce>[^"]+)".*mac="(?P<mac>[^"]+)"'
)


class FxATokenManager:
    """Manages FxA session tokens and key-fetch tokens in DynamoDB"""

    def __init__(
        self,
        table,
        session_ttl_seconds: int = 2592000,
        keyfetch_ttl_seconds: int = 300,
    ):
        """Initialize FxATokenManager.

        Args:
            table: DynamoDB Table resource (same auth table used by AuthAccountManager)
            session_ttl_seconds: Session token TTL (default 30 days)
            keyfetch_ttl_seconds: Key-fetch token TTL (default 5 minutes)
        """
        self.table = table
        self.session_ttl_seconds = session_ttl_seconds
        self.keyfetch_ttl_seconds = keyfetch_ttl_seconds

    def create_session_token(self, uid: str) -> bytes:
        """Create a new session token.

        1. Generate 32 random bytes (the raw token)
        2. Derive tokenId and reqHMACkey using fxa_crypto
        3. Store SESSION#{tokenId_hex} record in DynamoDB with uid, verified=True,
           createdAt, expiry (TTL), and reqHMACkey
        4. Return the raw token bytes (client needs this to derive tokenId + reqHMACkey)

        Args:
            uid: Account unique identifier

        Returns:
            32-byte raw token
        """
        token = fxa_crypto.generate_random_bytes(32)
        token_id = fxa_crypto.derive_token_id(token, SESSION_TOKEN_INFO)
        req_hmac_key = fxa_crypto.derive_req_hmac_key(token, SESSION_TOKEN_INFO)
        token_id_hex = token_id.hex()

        now = int(time.time())
        created_at = int(now * 1000)
        expiry = now + self.session_ttl_seconds

        self.table.put_item(
            Item={
                _PK: f"{SESSION_PREFIX}#{token_id_hex}",
                "uid": uid,
                "verified": True,
                "createdAt": created_at,
                "expiry": expiry,
                "reqHMACkey": req_hmac_key.hex(),
            }
        )

        return token

    def verify_session_token_id(self, token_id_hex: str) -> Optional[str]:
        """Verify a session token by its derived tokenId.

        Look up SESSION#{token_id_hex} in DynamoDB.
        Return uid if found and not expired, None otherwise.

        Args:
            token_id_hex: Hex-encoded tokenId

        Returns:
            uid if found and not expired, None otherwise
        """
        response = self.table.get_item(Key={_PK: f"{SESSION_PREFIX}#{token_id_hex}"})

        if "Item" not in response:
            return None

        item = response["Item"]

        # Check expiry server-side
        if item.get("expiry", 0) < int(time.time()):
            return None

        return item["uid"]

    def verify_session_hawk(
        self,
        authorization_header: str,
        method: str,
        path: str,
        host: str,
        port: str,
    ) -> Optional[str]:
        """Verify Hawk HMAC signature for session-authenticated routes.

        1. Parse Hawk header fields (id, ts, nonce, mac)
        2. Look up SESSION#{id} to get uid and reqHMACkey
        3. Check expiry
        4. Construct canonical string
        5. Compute HMAC-SHA256(reqHMACkey, canonical_string)
        6. Constant-time compare with provided mac
        7. Return uid on success, None on failure

        Args:
            authorization_header: Full Authorization header value
            method: HTTP method (GET, POST, etc.)
            path: Request path
            host: Request host
            port: Request port

        Returns:
            uid on success, None on failure
        """
        match = HAWK_HEADER_PATTERN.search(authorization_header)
        if not match:
            return None

        token_id_hex = match.group("id")
        ts = match.group("ts")
        nonce = match.group("nonce")
        mac_b64 = match.group("mac")

        # Look up session record
        response = self.table.get_item(Key={_PK: f"{SESSION_PREFIX}#{token_id_hex}"})
        if "Item" not in response:
            return None

        item = response["Item"]

        # Check expiry
        if item.get("expiry", 0) < int(time.time()):
            return None

        req_hmac_key_hex = item.get("reqHMACkey")
        if not req_hmac_key_hex:
            return None

        req_hmac_key = bytes.fromhex(req_hmac_key_hex)

        # Construct canonical string per Hawk spec
        canonical = f"hawk.1.header\n{ts}\n{nonce}\n{method}\n{path}\n{host}\n{port}\n\n\n"

        # Compute expected MAC
        computed_mac = hmac.new(req_hmac_key, canonical.encode("ascii"), hashlib.sha256).digest()
        computed_mac_b64 = base64.b64encode(computed_mac).decode("ascii")

        # Constant-time compare
        if not hmac.compare_digest(computed_mac_b64, mac_b64):
            return None

        return item["uid"]

    def verify_keyfetch_hawk(
        self,
        authorization_header: str,
        method: str,
        path: str,
        host: str,
        port: str,
    ) -> Optional[dict]:
        """Verify Hawk HMAC signature for key-fetch token authenticated routes.

        Atomically consumes the key-fetch token (single-use) while verifying
        the Hawk HMAC signature.

        Args:
            authorization_header: Full Authorization header value
            method: HTTP method (GET, POST, etc.)
            path: Request path
            host: Request host
            port: Request port

        Returns:
            Dict with uid and keyFetchToken on success, None on failure
        """
        match = HAWK_HEADER_PATTERN.search(authorization_header)
        if not match:
            return None

        token_id_hex = match.group("id")
        ts = match.group("ts")
        nonce = match.group("nonce")
        mac_b64 = match.group("mac")

        # Atomically consume the key-fetch token
        try:
            response = self.table.delete_item(
                Key={_PK: f"{KEYFETCH_PREFIX}#{token_id_hex}"},
                ReturnValues="ALL_OLD",
                ConditionExpression="attribute_exists(PK)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise

        item = response.get("Attributes")
        if not item:
            return None

        # Check expiry
        if item.get("expiry", 0) < int(time.time()):
            return None

        req_hmac_key_hex = item.get("reqHMACkey")
        if not req_hmac_key_hex:
            return None

        req_hmac_key = bytes.fromhex(req_hmac_key_hex)

        # Construct canonical string per Hawk spec
        canonical = f"hawk.1.header\n{ts}\n{nonce}\n{method}\n{path}\n{host}\n{port}\n\n\n"

        # Compute expected MAC
        computed_mac = hmac.new(req_hmac_key, canonical.encode("ascii"), hashlib.sha256).digest()
        computed_mac_b64 = base64.b64encode(computed_mac).decode("ascii")

        # Constant-time compare
        if not hmac.compare_digest(computed_mac_b64, mac_b64):
            return None

        return {
            "uid": item["uid"],
            "keyFetchToken": item["keyFetchToken"],
        }

    def create_key_fetch_token(self, uid: str) -> bytes:
        """Create a new key-fetch token.

        1. Generate 32 random bytes (the raw token)
        2. Derive tokenId and reqHMACkey using fxa_crypto
        3. Store KEYFETCH#{tokenId_hex} record with uid, raw token hex, reqHMACkey, expiry
        4. Return the raw token bytes

        Args:
            uid: Account unique identifier

        Returns:
            32-byte raw token
        """
        token = fxa_crypto.generate_random_bytes(32)
        token_id = fxa_crypto.derive_token_id(token, KEY_FETCH_TOKEN_INFO)
        req_hmac_key = fxa_crypto.derive_req_hmac_key(token, KEY_FETCH_TOKEN_INFO)
        token_id_hex = token_id.hex()

        now = int(time.time())
        expiry = now + self.keyfetch_ttl_seconds

        self.table.put_item(
            Item={
                _PK: f"{KEYFETCH_PREFIX}#{token_id_hex}",
                "uid": uid,
                "keyFetchToken": token.hex(),
                "reqHMACkey": req_hmac_key.hex(),
                "expiry": expiry,
            }
        )

        return token

    def consume_key_fetch_token(self, token_id_hex: str) -> Optional[dict]:
        """Consume (single-use) a key-fetch token atomically.

        Uses delete_item with ReturnValues to avoid TOCTOU race condition.

        Args:
            token_id_hex: Hex-encoded tokenId

        Returns:
            Dict with uid and keyFetchToken, or None if not found/expired
        """
        try:
            response = self.table.delete_item(
                Key={_PK: f"{KEYFETCH_PREFIX}#{token_id_hex}"},
                ReturnValues="ALL_OLD",
                ConditionExpression="attribute_exists(PK)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise

        item = response.get("Attributes")
        if not item:
            return None

        # Check expiry server-side
        if item.get("expiry", 0) < int(time.time()):
            return None

        return {
            "uid": item["uid"],
            "keyFetchToken": item["keyFetchToken"],
        }

    def delete_session(self, token_id_hex: str) -> None:
        """Delete a session token (for sign-out).

        Args:
            token_id_hex: Hex-encoded tokenId
        """
        self.table.delete_item(Key={_PK: f"{SESSION_PREFIX}#{token_id_hex}"})
