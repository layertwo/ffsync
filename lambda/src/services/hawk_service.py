"""
HAWK Authentication Service

Unified service for HAWK credential generation (Token Server) and validation (Storage Server).
Uses mohawk library for Hawk protocol validation.
"""

import base64
import binascii
import re
import secrets
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import mohawk
import mohawk.exc
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

from src.shared.exceptions import (
    AuthenticationException,
    ExpiredHawkTokenException,
    InvalidGenerationException,
    InvalidHawkHeaderException,
    InvalidHawkSignatureException,
)

logger = Logger(child=True)

# Pattern to extract hawk id from header without full parse
_HAWK_ID_PATTERN = re.compile(r'id="([^"]+)"')


@dataclass
class HawkCredentials:
    """HAWK credentials for token issuance and validation"""

    user_id: str
    generation: int
    expiry: int
    hawk_id: str
    hawk_key: Optional[str] = None  # Only populated when generating


class HawkService:
    """
    Unified HAWK service for both Token Server and Storage Server.

    Token Server uses:
        - generate_hawk_credentials()
        - store_token_in_cache()

    Storage Server uses:
        - validate()
    """

    def __init__(
        self, token_cache_table, timestamp_skew_tolerance: int = 60, token_duration: int = 300
    ):
        self.token_cache_table = token_cache_table
        self.timestamp_skew_tolerance = timestamp_skew_tolerance
        self.token_duration = token_duration

    def validate(
        self, authorization_header: str, method: str, path: str, host: str, port: int
    ) -> HawkCredentials:
        """
        Validate HAWK Authorization header and return credentials.

        Uses mohawk.Receiver for header parsing, timestamp validation, and MAC verification.
        Custom business logic (expiry, generation) runs in the credentials_map callback.
        """
        # Extract hawk_id for pre-validation of custom business logic
        hawk_id = self._extract_hawk_id(authorization_header)
        user_id, generation, expiry = self.decode_hawk_id(hawk_id)

        # Validate token hasn't expired (custom check, not part of Hawk protocol)
        if not self.validate_hawk_id_expiry(expiry):
            raise ExpiredHawkTokenException(f"HAWK token expired at {expiry}")

        # Credentials lookup called by mohawk during MAC verification
        def credentials_map(sender_id):
            hawk_key, cached_user_id, cached_generation = self.get_hawk_key_from_cache(sender_id)
            if cached_generation != generation:
                raise InvalidGenerationException(
                    f"Generation mismatch: expected {cached_generation}, got {generation}"
                )
            return {"id": sender_id, "key": hawk_key, "algorithm": "sha256"}

        # mohawk handles: header parsing, timestamp skew, normalized string, MAC verification
        try:
            mohawk.Receiver(
                credentials_map,
                authorization_header,
                f"https://{host}:{port}{path}",
                method,
                seen_nonce=self._seen_nonce,
                timestamp_skew_in_seconds=self.timestamp_skew_tolerance,
                accept_untrusted_content=True,
            )
        except (InvalidGenerationException, AuthenticationException):
            raise
        except mohawk.exc.MissingAuthorization:
            raise InvalidHawkHeaderException("Missing authorization header")
        except mohawk.exc.BadHeaderValue as e:
            raise InvalidHawkHeaderException(str(e))
        except mohawk.exc.MacMismatch:
            raise InvalidHawkSignatureException("HAWK MAC verification failed")
        except mohawk.exc.TokenExpired:
            raise InvalidHawkSignatureException("Timestamp outside acceptable window")
        except mohawk.exc.HawkFail as e:
            raise InvalidHawkSignatureException(str(e))

        logger.info(
            "HAWK authentication successful",
            extra={
                "method": method,
                "uri": path,
                "host": host,
                "port": port,
            },
        )

        return HawkCredentials(
            user_id=user_id, generation=generation, expiry=expiry, hawk_id=hawk_id
        )

    def _seen_nonce(self, sender_id, nonce, timestamp):
        """Check if a nonce has been seen before (replay protection).

        Uses DynamoDB conditional write: if the nonce record already exists,
        the request is a replay. Records auto-expire via DynamoDB TTL.
        """
        try:
            self.token_cache_table.put_item(
                Item={
                    "PK": f"NONCE#{sender_id}#{nonce}#{timestamp}",
                    "expiry": int(time.time()) + self.timestamp_skew_tolerance * 2,
                },
                ConditionExpression="attribute_not_exists(PK)",
            )
            return False  # New nonce
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return True  # Replay detected
            raise

    def _extract_hawk_id(self, authorization_header: str) -> str:
        """Extract the id field from a Hawk Authorization header."""
        if not authorization_header or not authorization_header.startswith("Hawk "):
            raise InvalidHawkHeaderException("Authorization header must start with 'Hawk '")
        match = _HAWK_ID_PATTERN.search(authorization_header)
        if not match:
            raise InvalidHawkHeaderException("Missing id in HAWK header")
        return match.group(1)

    def decode_hawk_id(self, hawk_id: str) -> Tuple[str, int, int]:
        """Decode HAWK ID back to user_id, generation, expiry."""
        try:
            padding = 4 - (len(hawk_id) % 4)
            if padding != 4:
                hawk_id += "=" * padding
            decoded = base64.urlsafe_b64decode(hawk_id).decode("utf-8")
            parts = decoded.split(":")
            if len(parts) != 3:
                raise ValueError("HAWK ID must have 3 parts")
            user_id, generation, expiry = parts
            return user_id, int(generation), int(expiry)
        except (ValueError, binascii.Error) as e:
            raise InvalidHawkHeaderException(f"Invalid HAWK ID format: {e}")

    def validate_hawk_id_expiry(self, expiry: int) -> bool:
        """Validate HAWK ID hasn't expired."""
        return int(time.time()) < expiry

    def get_hawk_key_from_cache(self, hawk_id: str) -> Tuple[str, str, int]:
        """Retrieve HAWK shared secret from token cache."""
        try:
            response = self.token_cache_table.get_item(Key={"PK": f"TOKEN#{hawk_id}"})
            if "Item" not in response:
                raise AuthenticationException(f"HAWK token not found: {hawk_id}")
            item = response["Item"]
            return (item["hawk_key"], item["user_id"], int(item["generation"]))
        except ClientError as e:
            logger.error(f"Failed to retrieve HAWK token from cache: {e}")
            raise AuthenticationException(f"Failed to retrieve HAWK token: {e}")

    # ========== Token Generation Methods (Token Server) ==========

    def generate_hawk_credentials(self, user_id: str, generation: int) -> HawkCredentials:
        """Generate HAWK credentials for token issuance."""
        expiry = int(time.time()) + self.token_duration
        hawk_id = self.generate_hawk_id(user_id, generation, expiry)
        hawk_key = self.generate_hawk_key()
        return HawkCredentials(
            user_id=user_id,
            generation=generation,
            expiry=expiry,
            hawk_id=hawk_id,
            hawk_key=hawk_key,
        )

    def generate_hawk_id(self, user_id: str, generation: int, expiry: int) -> str:
        """Generate HAWK identifier (URL-safe base64, no padding)."""
        id_string = f"{user_id}:{generation}:{expiry}"
        encoded = base64.urlsafe_b64encode(id_string.encode("utf-8")).decode("utf-8")
        return encoded.rstrip("=")

    def generate_hawk_key(self) -> str:
        """Generate cryptographically random HAWK shared secret (64-char hex)."""
        return secrets.token_bytes(32).hex()

    def store_token_in_cache(self, credentials: HawkCredentials) -> None:
        """Store issued HAWK token in DynamoDB cache."""
        self.token_cache_table.put_item(
            Item={
                "PK": f"TOKEN#{credentials.hawk_id}",
                "hawk_key": credentials.hawk_key,
                "user_id": credentials.user_id,
                "generation": credentials.generation,
                "expiry": credentials.expiry,
                "created_at": int(time.time()),
            }
        )
