"""
HAWK Authentication Service

Unified service for HAWK credential generation (Token Server) and validation (Storage Server).
"""

import base64
import binascii
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Optional, Tuple

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
        - All validation helper methods
    """

    TIMESTAMP_SKEW_SECONDS = 60  # Allow 60 second clock skew
    TOKEN_DURATION_SECONDS = 300  # 5 minutes

    def __init__(self, token_cache_table):
        """
        Initialize HAWK service with DynamoDB table.

        Args:
            token_cache_table: boto3 DynamoDB Table resource for token cache
        """
        self.token_cache_table = token_cache_table

    def validate(
        self, authorization_header: str, method: str, path: str, host: str, port: int
    ) -> HawkCredentials:
        """
        Validate HAWK Authorization header and return credentials.

        Args:
            authorization_header: HAWK Authorization header value
            method: HTTP method (GET, POST, etc.)
            path: Request path
            host: Request host
            port: Request port

        Returns:
            HawkCredentials with user_id, generation, expiry, hawk_id

        Raises:
            InvalidHawkHeaderException: Malformed HAWK header
            ExpiredHawkTokenException: Token expired
            InvalidHawkSignatureException: Signature verification failed
            InvalidGenerationException: Generation number mismatch

        HAWK Header Format:
            Hawk id="base64_encoded_id", ts="1702345678", nonce="random", mac="signature"

        HAWK ID Format (base64-encoded):
            {user_id}:{generation}:{expiry_timestamp}

        Validation Steps:
            1. Parse HAWK header and extract id, ts, nonce, mac, hash (optional)
            2. Decode HAWK ID and extract user_id, generation, expiry
            3. Verify token has not expired (current_time < expiry)
            4. Validate timestamp is within acceptable window
            5. Retrieve HAWK shared secret from TokenKeyStore
            6. Compute expected MAC using HMAC-SHA256
            7. Compare computed MAC with provided MAC (constant-time comparison)
        """
        # Parse HAWK header
        hawk_params = self.parse_hawk_header(authorization_header)
        hawk_id = hawk_params["id"]
        timestamp = int(hawk_params["ts"])
        nonce = hawk_params["nonce"]
        provided_mac = hawk_params["mac"]
        payload_hash = hawk_params.get("hash", "")  # Extract hash if present
        ext = hawk_params.get("ext", "")

        # Decode and validate HAWK ID
        user_id, generation, expiry = self.decode_hawk_id(hawk_id)

        # Validate token hasn't expired
        if not self.validate_hawk_id_expiry(expiry):
            raise ExpiredHawkTokenException(f"HAWK token expired at {expiry}")

        # Validate timestamp
        if not self.validate_timestamp(timestamp):
            raise InvalidHawkSignatureException(f"Timestamp {timestamp} outside acceptable window")

        # Retrieve HAWK key from cache
        hawk_key, cached_user_id, cached_generation = self.get_hawk_key_from_cache(hawk_id)

        # Verify generation matches
        if cached_generation != generation:
            raise InvalidGenerationException(
                f"Generation mismatch: expected {cached_generation}, got {generation}"
            )

        # Verify MAC (now including payload_hash and ext)
        if not self.verify_mac(
            hawk_key, provided_mac, timestamp, nonce, method, path, host, port, payload_hash, ext
        ):
            raise InvalidHawkSignatureException("HAWK MAC verification failed")

        return HawkCredentials(
            user_id=user_id, generation=generation, expiry=expiry, hawk_id=hawk_id
        )

    def parse_hawk_header(self, authorization_header: str) -> dict:
        """
        Parse HAWK Authorization header.

        Args:
            authorization_header: Full Authorization header value

        Returns:
            Dictionary with id, ts, nonce, mac keys

        Raises:
            InvalidHawkHeaderException: Malformed header

        Example:
            Hawk id="abc123", ts="1702345678", nonce="xyz", mac="signature=="
        """
        if not authorization_header.startswith("Hawk "):
            raise InvalidHawkHeaderException("Authorization header must start with 'Hawk '")

        # Parse key="value" pairs
        params = {}
        parts = authorization_header[5:].split(", ")  # Skip 'Hawk '
        for part in parts:
            if "=" not in part:
                raise InvalidHawkHeaderException(f"Invalid HAWK parameter: {part}")
            key, value = part.split("=", 1)
            params[key] = value.strip('"')

        # Validate required fields
        required = ["id", "ts", "nonce", "mac"]
        for field in required:
            if field not in params:
                raise InvalidHawkHeaderException(f"Missing required HAWK parameter: {field}")

        return params

    def decode_hawk_id(self, hawk_id: str) -> Tuple[str, int, int]:
        """
        Decode HAWK ID back to user_id, generation, expiry.

        Args:
            hawk_id: Base64-encoded HAWK ID

        Returns:
            Tuple of (user_id, generation, expiry)

        Raises:
            InvalidHawkHeaderException: Invalid format
        """
        try:
            # Add padding back if needed
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
        """
        Validate HAWK ID hasn't expired.

        Args:
            expiry: Unix timestamp when token expires

        Returns:
            True if token is still valid
        """
        return int(time.time()) < expiry

    def validate_timestamp(self, timestamp: int) -> bool:
        """
        Validate timestamp is within acceptable window.

        Args:
            timestamp: Unix timestamp from HAWK header

        Returns:
            True if timestamp is within acceptable skew
        """
        now = int(time.time())
        return abs(now - timestamp) <= self.TIMESTAMP_SKEW_SECONDS

    def build_normalized_string(
        self,
        timestamp: str,
        nonce: str,
        method: str,
        uri: str,
        host: str,
        port: str,
        payload_hash: str = "",
        ext: str = "",
    ) -> str:
        """
        Build the normalized request string for MAC calculation.

        HAWK Normalized Request String Format:
            hawk.1.header\n
            {timestamp}\n
            {nonce}\n
            {method}\n
            {uri}\n
            {host}\n
            {port}\n
            {payload_hash}\n
            {ext}\n
        """
        return (
            f"hawk.1.header\n"
            f"{timestamp}\n"
            f"{nonce}\n"
            f"{method.upper()}\n"
            f"{uri}\n"
            f"{host.lower()}\n"
            f"{port}\n"
            f"{payload_hash}\n"
            f"{ext}\n"
        )

    def calculate_mac(self, key: str, normalized_string: str) -> str:
        """
        Calculate HAWK MAC using HMAC-SHA256.

        Args:
            key: HAWK shared secret (as string, NOT hex-encoded)
            normalized_string: Normalized request string

        Returns:
            Base64-encoded MAC signature
        """
        # Use key as UTF-8 bytes directly (mohawk compatibility)
        mac = hmac.new(key.encode("utf-8"), normalized_string.encode("utf-8"), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode("utf-8")

    def verify_mac(
        self,
        hawk_key: str,
        provided_mac: str,
        timestamp: int,
        nonce: str,
        method: str,
        uri: str,
        host: str,
        port: int,
        payload_hash: str = "",
        ext: str = "",
    ) -> bool:
        """
        Verify the MAC from the Authorization header.

        Args:
            hawk_key: Hex-encoded HAWK shared secret
            provided_mac: MAC from Authorization header
            timestamp: Unix timestamp from header
            nonce: Nonce from header
            method: HTTP method
            uri: Request URI
            host: Request host
            port: Request port
            payload_hash: Optional payload hash
            ext: Optional extension data

        Returns:
            True if MAC is valid (constant-time comparison)
        """
        normalized = self.build_normalized_string(
            str(timestamp), nonce, method, uri, host, str(port), payload_hash, ext
        )
        expected_mac = self.calculate_mac(hawk_key, normalized)

        # Log MAC verification details for debugging
        logger.info(
            "HAWK MAC verification",
            extra={
                "method": method,
                "uri": uri,
                "host": host,
                "port": port,
                "timestamp": timestamp,
                "match": hmac.compare_digest(expected_mac, provided_mac),
            },
        )

        return hmac.compare_digest(expected_mac, provided_mac)

    def get_hawk_key_from_cache(self, hawk_id: str) -> Tuple[str, str, int]:
        """
        Retrieve HAWK shared secret from token cache.

        Args:
            hawk_id: Base64-encoded HAWK ID

        Returns:
            Tuple of (hawk_key, user_id, generation)

        Raises:
            AuthenticationException: Token not found in cache or DynamoDB error

        Token Cache Schema:
            PK: "TOKEN#{base64_hawk_id}"
            hawk_key: String (hex-encoded, 64 chars)
            user_id: String
            generation: Number
            expiry: Number (DynamoDB TTL attribute for auto-cleanup)
            created_at: Number
        """
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
        """
        Generate HAWK credentials for token issuance.

        Args:
            user_id: User identifier from OIDC sub claim
            generation: Current generation number

        Returns:
            HawkCredentials with hawk_id and hawk_key populated

        Used by Token Server when issuing tokens.
        """
        expiry = int(time.time()) + self.TOKEN_DURATION_SECONDS
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
        """
        Generate HAWK identifier (URL-safe base64).

        Format: {user_id}:{generation}:{expiry}

        Returns:
            Base64-encoded HAWK ID (without padding)
        """
        id_string = f"{user_id}:{generation}:{expiry}"
        encoded = base64.urlsafe_b64encode(id_string.encode("utf-8")).decode("utf-8")
        # Remove padding for cleaner URLs
        return encoded.rstrip("=")

    def generate_hawk_key(self) -> str:
        """
        Generate cryptographically random HAWK shared secret.

        Returns:
            64-character hex string (32 bytes of randomness, hex-encoded for storage)
            Note: This hex string is used as-is by mohawk, not decoded
        """
        return secrets.token_bytes(32).hex()

    def store_token_in_cache(self, credentials: HawkCredentials) -> None:
        """
        Store issued HAWK token in DynamoDB cache.

        Args:
            credentials: HawkCredentials with hawk_key populated

        Used by Token Server after generating credentials.
        """
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
