"""
FxA Crypto Module

Implements the Firefox Accounts "onepw" protocol key derivation functions
using HKDF-SHA256. This is the foundation for FxA-compatible authentication.

Reference: https://github.com/mozilla/fxa-auth-server/wiki/onepw-protocol
"""

import hashlib
import hmac
import os

from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

NAMESPACE = "identity.mozilla.com/picl/v1/"


def _hkdf(ikm: bytes, info: str, length: int = 32) -> bytes:
    """HKDF-SHA256 with empty salt.

    Args:
        ikm: Input keying material.
        info: Context and application-specific info string.
        length: Output length in bytes (default 32).

    Returns:
        Derived key material of the requested length.
    """
    hkdf = HKDF(
        algorithm=SHA256(),
        length=length,
        salt=None,
        info=info.encode("utf-8"),
    )
    return hkdf.derive(ikm)


def derive_auth_pw(quick_stretched_pw: bytes) -> bytes:
    """Derive authPW from quick-stretched password.

    HKDF(qsPW, info="identity.mozilla.com/picl/v1/authPW")

    Args:
        quick_stretched_pw: The quick-stretched password bytes.

    Returns:
        32-byte authPW.
    """
    return _hkdf(quick_stretched_pw, NAMESPACE + "authPW")


def derive_unwrap_bkey(quick_stretched_pw: bytes) -> bytes:
    """Derive unwrapBkey from quick-stretched password.

    HKDF(qsPW, info="identity.mozilla.com/picl/v1/unwrapBkey")

    Args:
        quick_stretched_pw: The quick-stretched password bytes.

    Returns:
        32-byte unwrapBkey.
    """
    return _hkdf(quick_stretched_pw, NAMESPACE + "unwrapBkey")


def derive_verify_hash(auth_pw: bytes) -> bytes:
    """Derive verifyHash from authPW.

    HKDF(authPW, info="identity.mozilla.com/picl/v1/verifyHash")

    Args:
        auth_pw: The authPW bytes.

    Returns:
        32-byte verifyHash.
    """
    return _hkdf(auth_pw, NAMESPACE + "verifyHash")


def _derive_token_keys(token: bytes, info: str) -> bytes:
    """Derive 96-byte key material from a token.

    The 96-byte output is split into three 32-byte segments:
    - bytes 0-32: tokenId
    - bytes 32-64: reqHMACkey
    - bytes 64-96: keyRequestKey

    Args:
        token: The token bytes.
        info: Context info string for HKDF.

    Returns:
        96-byte derived key material.
    """
    return _hkdf(token, info, length=96)


def derive_token_keys(token: bytes, info: str) -> tuple[bytes, bytes, bytes]:
    """Derive all three token keys in a single HKDF call.

    Returns:
        Tuple of (token_id, req_hmac_key, key_request_key), each 32 bytes.
    """
    derived = _derive_token_keys(token, info)
    return derived[:32], derived[32:64], derived[64:96]


def derive_token_id(token: bytes, info: str) -> bytes:
    """Derive tokenId (first 32 bytes of 96-byte HKDF output).

    Args:
        token: The token bytes.
        info: Context info string for HKDF.

    Returns:
        32-byte tokenId.
    """
    return _derive_token_keys(token, info)[:32]


def derive_req_hmac_key(token: bytes, info: str) -> bytes:
    """Derive reqHMACkey (bytes 32-64 of 96-byte HKDF output).

    Args:
        token: The token bytes.
        info: Context info string for HKDF.

    Returns:
        32-byte reqHMACkey.
    """
    return _derive_token_keys(token, info)[32:64]


def derive_key_request_key(token: bytes, info: str) -> bytes:
    """Derive keyRequestKey (bytes 64-96 of 96-byte HKDF output).

    Args:
        token: The token bytes.
        info: Context info string for HKDF.

    Returns:
        32-byte keyRequestKey.
    """
    return _derive_token_keys(token, info)[64:96]


def encrypt_key_bundle(key_request_key: bytes, k_a: bytes, wrap_kb: bytes) -> bytes:
    """Encrypt kA + wrapKB into a key bundle.

    Steps:
    1. keys = HKDF(keyRequestKey, info="identity.mozilla.com/picl/v1/account/keys", length=96)
    2. hmacKey = keys[0:32], xorKey = keys[32:96]
    3. ciphertext = (kA || wrapKB) XOR xorKey
    4. mac = HMAC-SHA256(hmacKey, ciphertext)
    5. return ciphertext || mac

    Args:
        key_request_key: The keyRequestKey bytes.
        k_a: 32-byte kA key.
        wrap_kb: 32-byte wrapKB key.

    Returns:
        96-byte bundle (64-byte ciphertext + 32-byte HMAC).
    """
    keys = _hkdf(key_request_key, NAMESPACE + "account/keys", length=96)
    hmac_key = keys[:32]
    xor_key = keys[32:96]

    plaintext = k_a + wrap_kb
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, xor_key))

    mac = hmac.new(hmac_key, ciphertext, hashlib.sha256).digest()
    return ciphertext + mac


def generate_random_bytes(length: int = 32) -> bytes:
    """Generate cryptographically random bytes.

    Args:
        length: Number of random bytes to generate (default 32).

    Returns:
        Random bytes of the requested length.
    """
    return os.urandom(length)


def constant_time_compare(a: bytes, b: bytes) -> bool:
    """Constant-time byte comparison.

    Uses hmac.compare_digest to prevent timing attacks.

    Args:
        a: First byte string.
        b: Second byte string.

    Returns:
        True if a and b are equal, False otherwise.
    """
    return hmac.compare_digest(a, b)
