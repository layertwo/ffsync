"""Tests for FxA Crypto Module

Tests the FxA onepw protocol key derivation functions using HKDF-SHA256.
"""

from src.services.fxa_crypto import (
    NAMESPACE,
    constant_time_compare,
    derive_auth_pw,
    derive_key_request_key,
    derive_req_hmac_key,
    derive_token_id,
    derive_token_keys,
    derive_unwrap_bkey,
    derive_verify_hash,
    encrypt_key_bundle,
    generate_random_bytes,
)


class TestNamespace:
    """Tests for the NAMESPACE constant."""

    def test_namespace_value(self):
        """Test that NAMESPACE matches the FxA protocol namespace."""
        assert NAMESPACE == "identity.mozilla.com/picl/v1/"


class TestDeriveAuthPw:
    """Tests for derive_auth_pw function."""

    def test_returns_32_bytes(self):
        """Test that derive_auth_pw returns exactly 32 bytes."""
        qs_pw = b"\x00" * 32
        result = derive_auth_pw(qs_pw)
        assert len(result) == 32

    def test_returns_bytes(self):
        """Test that derive_auth_pw returns bytes type."""
        qs_pw = b"\x00" * 32
        result = derive_auth_pw(qs_pw)
        assert isinstance(result, bytes)

    def test_deterministic(self):
        """Test that the same input produces the same output."""
        qs_pw = b"\xab\xcd" * 16
        result1 = derive_auth_pw(qs_pw)
        result2 = derive_auth_pw(qs_pw)
        assert result1 == result2

    def test_differs_from_unwrap_bkey(self):
        """Test that authPW differs from unwrapBKey for the same input."""
        qs_pw = b"\x01\x02\x03" * 11  # 33 bytes, arbitrary length
        auth_pw = derive_auth_pw(qs_pw)
        unwrap_bkey = derive_unwrap_bkey(qs_pw)
        assert auth_pw != unwrap_bkey

    def test_different_inputs_produce_different_outputs(self):
        """Test that different inputs produce different outputs."""
        result1 = derive_auth_pw(b"\x00" * 32)
        result2 = derive_auth_pw(b"\x01" * 32)
        assert result1 != result2


class TestDeriveUnwrapBkey:
    """Tests for derive_unwrap_bkey function."""

    def test_returns_32_bytes(self):
        """Test that derive_unwrap_bkey returns exactly 32 bytes."""
        qs_pw = b"\x00" * 32
        result = derive_unwrap_bkey(qs_pw)
        assert len(result) == 32

    def test_returns_bytes(self):
        """Test that derive_unwrap_bkey returns bytes type."""
        qs_pw = b"\x00" * 32
        result = derive_unwrap_bkey(qs_pw)
        assert isinstance(result, bytes)

    def test_deterministic(self):
        """Test that the same input produces the same output."""
        qs_pw = b"\xab\xcd" * 16
        result1 = derive_unwrap_bkey(qs_pw)
        result2 = derive_unwrap_bkey(qs_pw)
        assert result1 == result2

    def test_different_inputs_produce_different_outputs(self):
        """Test that different inputs produce different outputs."""
        result1 = derive_unwrap_bkey(b"\x00" * 32)
        result2 = derive_unwrap_bkey(b"\x01" * 32)
        assert result1 != result2


class TestDeriveVerifyHash:
    """Tests for derive_verify_hash function."""

    def test_returns_32_bytes(self):
        """Test that derive_verify_hash returns exactly 32 bytes."""
        auth_pw = b"\x00" * 32
        result = derive_verify_hash(auth_pw)
        assert len(result) == 32

    def test_returns_bytes(self):
        """Test that derive_verify_hash returns bytes type."""
        auth_pw = b"\x00" * 32
        result = derive_verify_hash(auth_pw)
        assert isinstance(result, bytes)

    def test_deterministic(self):
        """Test that the same input produces the same output."""
        auth_pw = b"\xab\xcd" * 16
        result1 = derive_verify_hash(auth_pw)
        result2 = derive_verify_hash(auth_pw)
        assert result1 == result2

    def test_different_inputs_produce_different_outputs(self):
        """Test that different inputs produce different outputs."""
        result1 = derive_verify_hash(b"\x00" * 32)
        result2 = derive_verify_hash(b"\x01" * 32)
        assert result1 != result2

    def test_chained_derivation(self):
        """Test that derive_verify_hash(derive_auth_pw(qsPW)) works correctly."""
        qs_pw = b"\xaa" * 32
        auth_pw = derive_auth_pw(qs_pw)
        verify_hash = derive_verify_hash(auth_pw)
        assert len(verify_hash) == 32
        assert verify_hash != auth_pw


class TestDeriveTokenId:
    """Tests for derive_token_id function."""

    def test_returns_32_bytes(self):
        """Test that derive_token_id returns exactly 32 bytes."""
        token = b"\x00" * 32
        result = derive_token_id(token, "identity.mozilla.com/picl/v1/sessionToken")
        assert len(result) == 32

    def test_returns_bytes(self):
        """Test that derive_token_id returns bytes type."""
        token = b"\x00" * 32
        result = derive_token_id(token, "identity.mozilla.com/picl/v1/sessionToken")
        assert isinstance(result, bytes)

    def test_deterministic(self):
        """Test that the same inputs produce the same output."""
        token = b"\xab\xcd" * 16
        info = "identity.mozilla.com/picl/v1/sessionToken"
        result1 = derive_token_id(token, info)
        result2 = derive_token_id(token, info)
        assert result1 == result2

    def test_differs_from_req_hmac_key(self):
        """Test that tokenId differs from reqHMACkey for the same input."""
        token = b"\x00" * 32
        info = "identity.mozilla.com/picl/v1/sessionToken"
        token_id = derive_token_id(token, info)
        req_hmac_key = derive_req_hmac_key(token, info)
        assert token_id != req_hmac_key

    def test_differs_from_key_request_key(self):
        """Test that tokenId differs from keyRequestKey for the same input."""
        token = b"\x00" * 32
        info = "identity.mozilla.com/picl/v1/keyFetchToken"
        token_id = derive_token_id(token, info)
        key_request_key = derive_key_request_key(token, info)
        assert token_id != key_request_key


class TestDeriveReqHmacKey:
    """Tests for derive_req_hmac_key function."""

    def test_returns_32_bytes(self):
        """Test that derive_req_hmac_key returns exactly 32 bytes."""
        token = b"\x00" * 32
        result = derive_req_hmac_key(token, "identity.mozilla.com/picl/v1/sessionToken")
        assert len(result) == 32

    def test_returns_bytes(self):
        """Test that derive_req_hmac_key returns bytes type."""
        token = b"\x00" * 32
        result = derive_req_hmac_key(token, "identity.mozilla.com/picl/v1/sessionToken")
        assert isinstance(result, bytes)

    def test_deterministic(self):
        """Test that the same inputs produce the same output."""
        token = b"\xab\xcd" * 16
        info = "identity.mozilla.com/picl/v1/sessionToken"
        result1 = derive_req_hmac_key(token, info)
        result2 = derive_req_hmac_key(token, info)
        assert result1 == result2

    def test_differs_from_key_request_key(self):
        """Test that reqHMACkey differs from keyRequestKey for the same input."""
        token = b"\x00" * 32
        info = "identity.mozilla.com/picl/v1/keyFetchToken"
        req_hmac_key = derive_req_hmac_key(token, info)
        key_request_key = derive_key_request_key(token, info)
        assert req_hmac_key != key_request_key


class TestDeriveKeyRequestKey:
    """Tests for derive_key_request_key function."""

    def test_returns_32_bytes(self):
        """Test that derive_key_request_key returns exactly 32 bytes."""
        token = b"\x00" * 32
        result = derive_key_request_key(token, "identity.mozilla.com/picl/v1/keyFetchToken")
        assert len(result) == 32

    def test_returns_bytes(self):
        """Test that derive_key_request_key returns bytes type."""
        token = b"\x00" * 32
        result = derive_key_request_key(token, "identity.mozilla.com/picl/v1/keyFetchToken")
        assert isinstance(result, bytes)

    def test_deterministic(self):
        """Test that the same inputs produce the same output."""
        token = b"\xab\xcd" * 16
        info = "identity.mozilla.com/picl/v1/keyFetchToken"
        result1 = derive_key_request_key(token, info)
        result2 = derive_key_request_key(token, info)
        assert result1 == result2


class TestTokenDerivedKeysAllDifferent:
    """Tests that all three token-derived keys differ from each other."""

    def test_all_three_keys_differ(self):
        """Test that tokenId, reqHMACkey, and keyRequestKey are all distinct."""
        token = b"\x42" * 32
        info = "identity.mozilla.com/picl/v1/keyFetchToken"

        token_id = derive_token_id(token, info)
        req_hmac_key = derive_req_hmac_key(token, info)
        key_request_key = derive_key_request_key(token, info)

        assert token_id != req_hmac_key
        assert token_id != key_request_key
        assert req_hmac_key != key_request_key

    def test_different_info_produces_different_keys(self):
        """Test that different info strings produce different derived keys."""
        token = b"\x42" * 32
        info1 = "identity.mozilla.com/picl/v1/sessionToken"
        info2 = "identity.mozilla.com/picl/v1/keyFetchToken"

        token_id1 = derive_token_id(token, info1)
        token_id2 = derive_token_id(token, info2)
        assert token_id1 != token_id2


class TestEncryptKeyBundle:
    """Tests for encrypt_key_bundle function."""

    def test_returns_96_bytes(self):
        """Test that encrypt_key_bundle returns exactly 96 bytes (64 ciphertext + 32 HMAC)."""
        key_request_key = b"\x00" * 32
        k_a = b"\x11" * 32
        wrap_kb = b"\x22" * 32
        result = encrypt_key_bundle(key_request_key, k_a, wrap_kb)
        assert len(result) == 96

    def test_returns_bytes(self):
        """Test that encrypt_key_bundle returns bytes type."""
        key_request_key = b"\x00" * 32
        k_a = b"\x11" * 32
        wrap_kb = b"\x22" * 32
        result = encrypt_key_bundle(key_request_key, k_a, wrap_kb)
        assert isinstance(result, bytes)

    def test_ciphertext_differs_from_plaintext(self):
        """Test that the ciphertext portion differs from the plaintext (kA || wrapKB)."""
        key_request_key = b"\xaa" * 32
        k_a = b"\x11" * 32
        wrap_kb = b"\x22" * 32
        result = encrypt_key_bundle(key_request_key, k_a, wrap_kb)
        ciphertext = result[:64]
        plaintext = k_a + wrap_kb
        assert ciphertext != plaintext

    def test_deterministic(self):
        """Test that the same inputs produce the same output."""
        key_request_key = b"\xaa" * 32
        k_a = b"\x11" * 32
        wrap_kb = b"\x22" * 32
        result1 = encrypt_key_bundle(key_request_key, k_a, wrap_kb)
        result2 = encrypt_key_bundle(key_request_key, k_a, wrap_kb)
        assert result1 == result2

    def test_different_keys_produce_different_output(self):
        """Test that different keyRequestKeys produce different bundles."""
        k_a = b"\x11" * 32
        wrap_kb = b"\x22" * 32
        result1 = encrypt_key_bundle(b"\xaa" * 32, k_a, wrap_kb)
        result2 = encrypt_key_bundle(b"\xbb" * 32, k_a, wrap_kb)
        assert result1 != result2

    def test_mac_is_last_32_bytes(self):
        """Test that the MAC (last 32 bytes) is a valid HMAC-SHA256 digest length."""
        key_request_key = b"\xaa" * 32
        k_a = b"\x11" * 32
        wrap_kb = b"\x22" * 32
        result = encrypt_key_bundle(key_request_key, k_a, wrap_kb)
        mac = result[64:]
        assert len(mac) == 32


class TestGenerateRandomBytes:
    """Tests for generate_random_bytes function."""

    def test_default_length(self):
        """Test that default length is 32 bytes."""
        result = generate_random_bytes()
        assert len(result) == 32

    def test_custom_length(self):
        """Test generation with custom length."""
        result = generate_random_bytes(64)
        assert len(result) == 64

    def test_returns_bytes(self):
        """Test that generate_random_bytes returns bytes type."""
        result = generate_random_bytes()
        assert isinstance(result, bytes)

    def test_different_each_call(self):
        """Test that successive calls produce different values."""
        result1 = generate_random_bytes()
        result2 = generate_random_bytes()
        assert result1 != result2


class TestConstantTimeCompare:
    """Tests for constant_time_compare function."""

    def test_equal_bytes_returns_true(self):
        """Test that equal byte strings return True."""
        a = b"\x01\x02\x03"
        assert constant_time_compare(a, a) is True

    def test_equal_values_returns_true(self):
        """Test that equal-valued byte strings return True."""
        a = b"\x01\x02\x03"
        b = b"\x01\x02\x03"
        assert constant_time_compare(a, b) is True

    def test_different_bytes_returns_false(self):
        """Test that different byte strings return False."""
        a = b"\x01\x02\x03"
        b = b"\x04\x05\x06"
        assert constant_time_compare(a, b) is False

    def test_different_lengths_returns_false(self):
        """Test that byte strings of different lengths return False."""
        a = b"\x01\x02\x03"
        b = b"\x01\x02"
        assert constant_time_compare(a, b) is False

    def test_empty_bytes_returns_true(self):
        """Test that two empty byte strings return True."""
        assert constant_time_compare(b"", b"") is True


class TestKnownVectors:
    """Regression tests with pinned HKDF outputs to catch protocol-breaking changes."""

    def test_derive_auth_pw_known_vector(self):
        """Test derive_auth_pw against a pinned output for bytes(32)."""
        qs_pw = bytes(32)
        result = derive_auth_pw(qs_pw)
        assert result.hex() == "addd287a170e5d4ab0a06a143a64fe3c6ab805ad0be1a38bd1ba5093c8fe124d"

    def test_derive_verify_hash_chained_known_vector(self):
        """Test derive_verify_hash(derive_auth_pw(bytes(32))) against a pinned output."""
        auth_pw = derive_auth_pw(bytes(32))
        result = derive_verify_hash(auth_pw)
        assert result.hex() == "b1873a935b3c91146743a9292107634b314a3ae6daf859f7fc0f986da557c27e"

    def test_derive_unwrap_bkey_known_vector(self):
        """Test derive_unwrap_bkey against a pinned output for bytes(32)."""
        qs_pw = bytes(32)
        result = derive_unwrap_bkey(qs_pw)
        assert result.hex() == "ad0e1de4f2362227e01eba2764d8d97c38ee1886bc13bcaa5d98690f0dee7781"

    def test_encrypt_key_bundle_known_vector(self):
        """Test encrypt_key_bundle against a pinned 96-byte output for bytes(32) inputs."""
        result = encrypt_key_bundle(bytes(32), bytes(32), bytes(32))
        assert (
            result.hex() == "a274ea221b830275b783f65353fd6205edddcc383cdc842b68e651c5d7ceae23"
            "9eda060c3d1faabea47669a1a3c4c7767ad8db95ae7095f5ebe00a0283513210"
            "24239f73c36e0b245252ccb77b1eee19005aeeabdfbc3dec09adbca75dc66cff"
        )


class TestDeriveTokenKeys:
    """Tests for derive_token_keys function."""

    def test_returns_three_32_byte_keys(self):
        """Test that derive_token_keys returns a tuple of three 32-byte keys."""
        token = b"\x00" * 32
        info = "identity.mozilla.com/picl/v1/sessionToken"
        token_id, req_hmac_key, key_request_key = derive_token_keys(token, info)
        assert len(token_id) == 32
        assert len(req_hmac_key) == 32
        assert len(key_request_key) == 32

    def test_returns_tuple(self):
        """Test that derive_token_keys returns a tuple."""
        token = b"\x00" * 32
        info = "identity.mozilla.com/picl/v1/sessionToken"
        result = derive_token_keys(token, info)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_matches_individual_derivations(self):
        """Test that derive_token_keys matches the individual derivation functions."""
        token = b"\x42" * 32
        info = "identity.mozilla.com/picl/v1/keyFetchToken"
        token_id, req_hmac_key, key_request_key = derive_token_keys(token, info)
        assert token_id == derive_token_id(token, info)
        assert req_hmac_key == derive_req_hmac_key(token, info)
        assert key_request_key == derive_key_request_key(token, info)

    def test_deterministic(self):
        """Test that the same inputs produce the same outputs."""
        token = b"\xab\xcd" * 16
        info = "identity.mozilla.com/picl/v1/sessionToken"
        result1 = derive_token_keys(token, info)
        result2 = derive_token_keys(token, info)
        assert result1 == result2

    def test_all_three_keys_differ(self):
        """Test that all three returned keys are distinct."""
        token = b"\x42" * 32
        info = "identity.mozilla.com/picl/v1/keyFetchToken"
        token_id, req_hmac_key, key_request_key = derive_token_keys(token, info)
        assert token_id != req_hmac_key
        assert token_id != key_request_key
        assert req_hmac_key != key_request_key
