"""FxA Token Manager for session tokens and key-fetch tokens in DynamoDB"""

import hashlib
import hmac as hmac_mod
import re
import time
from base64 import b64encode
from typing import Optional
from urllib.parse import urlparse

import mohawk
import mohawk.exc
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

from src.services import fxa_crypto

logger = Logger(child=True)

_HAWK_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')

_PK = "PK"
SESSION_TOKEN_INFO = "identity.mozilla.com/picl/v1/sessionToken"
KEY_FETCH_TOKEN_INFO = "identity.mozilla.com/picl/v1/keyFetchToken"

SESSION_PREFIX = "SESSION"
KEYFETCH_PREFIX = "KEYFETCH"


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

    def _seen_nonce(self, sender_id, nonce, timestamp):
        """Check if a nonce has been seen before (replay protection).

        Uses DynamoDB conditional write: if the nonce record already exists,
        the request is a replay. Records auto-expire via DynamoDB TTL.
        """
        try:
            self.table.put_item(
                Item={
                    _PK: f"NONCE#{sender_id}#{nonce}#{timestamp}",
                    "expiry": int(time.time()) + 120,
                },
                ConditionExpression=f"attribute_not_exists({_PK})",
            )
            return False  # New nonce
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return True  # Replay detected
            raise

    def _verify_hawk(self, authorization_header, method, path, host, port, credentials_map):
        """Verify Hawk signature using mohawk.Receiver.

        Returns True on success, False on any authentication failure.
        The credentials_map callback handles credential lookup and may
        populate external state (e.g. uid) via closure side effects.
        """
        if not authorization_header:
            return False
        uri = f"https://{host}:{port}{path}"
        try:
            mohawk.Receiver(
                credentials_map,
                authorization_header,
                uri,
                method,
                seen_nonce=self._seen_nonce,
                accept_untrusted_content=True,
                timestamp_skew_in_seconds=60,
            )
            return True
        except mohawk.exc.HawkFail as e:
            # Parse header and compute normalized string for diagnostics
            attrs = dict(_HAWK_ATTR_RE.findall(authorization_header or ""))
            normalized = ""
            if attrs.get("ts") and attrs.get("nonce"):
                from urllib.parse import urlparse

                parsed = urlparse(uri)
                res_port = str(parsed.port or (443 if parsed.scheme == "https" else 80))
                resource = parsed.path + ("?" + parsed.query if parsed.query else "")
                normalized = (
                    f"hawk.1.header\n{attrs['ts']}\n{attrs['nonce']}\n"
                    f"{method}\n{resource}\n{parsed.hostname}\n{res_port}\n"
                    f"{attrs.get('hash', '')}\n{attrs.get('ext', '')}\n"
                )
            logger.warning(
                "Hawk verification failed",
                extra={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "uri": uri,
                    "method": method,
                    "host": host,
                    "port": port,
                    "path": path,
                    "auth_header": authorization_header or "",
                    "normalized_string": repr(normalized),
                },
            )
            return False

    def verify_session_hawk(
        self,
        authorization_header: str,
        method: str,
        path: str,
        host: str,
        port: str,
    ) -> Optional[str]:
        """Verify Hawk HMAC signature for session-authenticated routes."""
        uid_holder = {}
        key_holder = {}

        def credentials_map(sender_id):
            logger.info(
                "Session Hawk credential lookup",
                extra={
                    "sender_id_prefix": sender_id[:16],
                    "pk": f"{SESSION_PREFIX}#{sender_id[:16]}...",
                },
            )
            response = self.table.get_item(Key={_PK: f"{SESSION_PREFIX}#{sender_id}"})
            if "Item" not in response:
                raise mohawk.exc.CredentialsLookupError("Session not found")
            item = response["Item"]
            if item.get("expiry", 0) < int(time.time()):
                raise mohawk.exc.CredentialsLookupError("Session expired")
            key = item.get("reqHMACkey")
            if not key:
                raise mohawk.exc.CredentialsLookupError("Missing HMAC key")
            uid_holder["uid"] = item["uid"]
            key_holder["key"] = key
            logger.info(
                "Session Hawk credentials found",
                extra={"key_prefix": key[:16], "key_len": len(key), "uid": item["uid"]},
            )
            return {"id": sender_id, "key": key, "algorithm": "sha256"}

        if not self._verify_hawk(authorization_header, method, path, host, port, credentials_map):
            # Manual MAC computation with both key formats for diagnostics
            stored_key_hex = key_holder.get("key", "")
            if stored_key_hex:
                attrs = dict(_HAWK_ATTR_RE.findall(authorization_header or ""))
                uri = f"https://{host}:{port}{path}"
                parsed = urlparse(uri)
                res_port = str(parsed.port or (443 if parsed.scheme == "https" else 80))
                resource = parsed.path + ("?" + parsed.query if parsed.query else "")
                normalized = (
                    f"hawk.1.header\n{attrs.get('ts', '')}\n{attrs.get('nonce', '')}\n"
                    f"{method}\n{resource}\n{parsed.hostname}\n{res_port}\n"
                    f"{attrs.get('hash', '')}\n{attrs.get('ext', '')}\n"
                )
                # Format 1: hex string as ASCII bytes (what mohawk does)
                mac_hex_ascii = b64encode(
                    hmac_mod.new(
                        stored_key_hex.encode("ascii"),
                        normalized.encode("utf-8"),
                        hashlib.sha256,
                    ).digest()
                ).decode("ascii")
                # Format 2: raw bytes from hex decoding (what old code did)
                mac_raw_bytes = b64encode(
                    hmac_mod.new(
                        bytes.fromhex(stored_key_hex),
                        normalized.encode("utf-8"),
                        hashlib.sha256,
                    ).digest()
                ).decode("ascii")
                client_mac = attrs.get("mac", "")
                logger.warning(
                    "Manual MAC comparison",
                    extra={
                        "mac_hex_ascii_key": mac_hex_ascii,
                        "mac_raw_bytes_key": mac_raw_bytes,
                        "client_mac": client_mac,
                        "hex_ascii_matches": mac_hex_ascii == client_mac,
                        "raw_bytes_matches": mac_raw_bytes == client_mac,
                    },
                )
            return None
        return uid_holder.get("uid")

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
        """
        result_holder = {}

        def credentials_map(sender_id):
            try:
                response = self.table.delete_item(
                    Key={_PK: f"{KEYFETCH_PREFIX}#{sender_id}"},
                    ReturnValues="ALL_OLD",
                    ConditionExpression="attribute_exists(PK)",
                )
            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    raise mohawk.exc.CredentialsLookupError("Token not found")
                raise
            item = response.get("Attributes")
            if not item:
                raise mohawk.exc.CredentialsLookupError("Token not found")
            if item.get("expiry", 0) < int(time.time()):
                raise mohawk.exc.CredentialsLookupError("Token expired")
            key = item.get("reqHMACkey")
            if not key:
                raise mohawk.exc.CredentialsLookupError("Missing HMAC key")
            result_holder["uid"] = item["uid"]
            result_holder["keyFetchToken"] = item["keyFetchToken"]
            return {"id": sender_id, "key": key, "algorithm": "sha256"}

        if not self._verify_hawk(authorization_header, method, path, host, port, credentials_map):
            return None

        if "uid" not in result_holder:
            return None

        return {
            "uid": result_holder["uid"],
            "keyFetchToken": result_holder["keyFetchToken"],
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
