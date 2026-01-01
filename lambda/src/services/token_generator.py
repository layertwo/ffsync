"""Token generator for Firefox Sync HAWK credentials"""

import hashlib

from src.services.hawk_service import HawkService
from src.shared.token import TokenResponse


class TokenGenerator:
    """Generates HAWK credentials and token responses for Firefox Sync clients"""

    # Hash algorithm for HAWK
    HASH_ALGORITHM = "sha256"

    def __init__(self, storage_domain: str, hawk_service: HawkService):
        """Initialize TokenGenerator

        Args:
            storage_domain: domain for the storage API (e.g., "storage.sync.example.com")
            hawk_service: HawkService instance for HAWK credential generation
        """
        self._storage_domain = storage_domain
        self._hawk_service = hawk_service

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
        # Generate HAWK credentials using HawkService
        credentials = self._hawk_service.generate_hawk_credentials(user_id, generation)

        # Store token in cache for Storage Server validation
        self._hawk_service.store_token_in_cache(credentials)

        # Compute api_endpoint dynamically using derived uid
        api_endpoint = f"https://{self._storage_domain}/1.5/{uid}"

        # hawk_key is always populated by generate_hawk_credentials()
        assert credentials.hawk_key is not None, "HAWK key must be present for token generation"

        return TokenResponse(
            id=credentials.hawk_id,
            key=credentials.hawk_key,
            api_endpoint=api_endpoint,
            uid=uid,
            duration=self._hawk_service.TOKEN_DURATION_SECONDS,
            hashalg=self.HASH_ALGORITHM,
        )
