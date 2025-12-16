"""Token generator for Firefox Sync HAWK credentials"""

import base64
import hashlib
import secrets
import time

from src.shared.token import TokenResponse


class TokenGenerator:
    """Generates HAWK credentials and token responses for Firefox Sync clients"""

    # Token duration in seconds (5 minutes)
    TOKEN_DURATION = 300

    # Hash algorithm for HAWK
    HASH_ALGORITHM = "sha256"

    # HAWK key size in bytes
    HAWK_KEY_SIZE = 32

    def __init__(self, storage_domain: str):
        """Initialize TokenGenerator

        Args:
            storage_domain: domain for the storage API (e.g., "storage.sync.example.com")
        """
        self._storage_domain = storage_domain

    def generate_hawk_id(self, user_id: str, generation: int, expiry: int) -> str:
        """Generate HAWK identifier as URL-safe base64-encoded string

        The HAWK ID encodes user_id:generation:expiry to enable stateless
        validation by the Storage API.

        Args:
            user_id: User identifier from OIDC sub claim (stable)
            generation: Current generation number for token invalidation
            expiry: Token expiry timestamp (Unix epoch seconds)

        Returns:
            URL-safe base64-encoded string containing user_id:generation:expiry
        """
        payload = f"{user_id}:{generation}:{expiry}"
        encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")
        # Remove padding for cleaner URLs
        return encoded.rstrip("=")

    def generate_hawk_key(self) -> str:
        """Generate cryptographically random HAWK shared secret

        Uses secrets.token_bytes() for cryptographic randomness.

        Returns:
            64-character hexadecimal string (32 bytes)
        """
        return secrets.token_bytes(self.HAWK_KEY_SIZE).hex()

    def generate_uid(self, user_id: str, generation: int) -> int:
        """Generate numeric user ID from user identifier and generation

        Creates a numeric UID by hashing user_id + generation.
        The uid changes when generation changes (node reset).
        Uses first 8 bytes of SHA-256 hash as unsigned integer.

        Args:
            user_id: User identifier from OIDC sub claim
            generation: Current generation number

        Returns:
            Positive integer derived from user_id and generation hash
        """
        # Combine user_id and generation for hashing
        combined = f"{user_id}:{generation}"
        hash_bytes = hashlib.sha256(combined.encode("utf-8")).digest()
        # Use first 8 bytes as unsigned 64-bit integer, then mask to ensure positive
        uid = int.from_bytes(hash_bytes[:8], byteorder="big") & 0x7FFFFFFFFFFFFFFF
        return uid

    def generate_token(self, user_id: str, uid: int, generation: int) -> TokenResponse:
        """Generate complete token response with HAWK credentials

        Constructs a TokenResponse with all required fields for Firefox Sync:
        - id: HAWK identifier (base64-encoded user_id:generation:expiry)
        - key: HAWK shared secret (hex-encoded random bytes)
        - api_endpoint: Full storage API URL
        - uid: Numeric user ID (derived, changes on node reset)
        - duration: Token validity in seconds (300)
        - hashalg: Hash algorithm for HAWK ("sha256")

        Args:
            user_id: User identifier from OIDC sub claim (stable)
            uid: Numeric user identifier (derived from user_id + generation)
            generation: Current generation number

        Returns:
            TokenResponse with all HAWK credentials and metadata
        """
        # Calculate expiry timestamp
        current_time = int(time.time())
        expiry = current_time + self.TOKEN_DURATION

        # Generate HAWK credentials with stable user_id
        hawk_id = self.generate_hawk_id(user_id, generation, expiry)
        hawk_key = self.generate_hawk_key()

        # Compute api_endpoint dynamically using derived uid
        api_endpoint = f"https://{self._storage_domain}/1.5/{uid}"

        return TokenResponse(
            id=hawk_id,
            key=hawk_key,
            api_endpoint=api_endpoint,
            uid=uid,
            duration=self.TOKEN_DURATION,
            hashalg=self.HASH_ALGORITHM,
        )
