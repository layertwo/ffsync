# FxA Auth Shim Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable Firefox's native "Sign in to Sync" by implementing a minimal FxA-compatible auth server consolidated with the existing token server.

**Architecture:** Extend the existing token server Lambda with FxA account management, session tokens, OAuth, and key derivation endpoints. Extend the frontend SPA with WebChannel-based sign-in pages. Rename Service.TOKEN to Service.AUTH, add a DynamoDB table for auth state, and a KMS key for JWT signing.

**Tech Stack:** Python 3.14, AWS Lambda (Powertools), DynamoDB, KMS, Smithy, CDK, React + TypeScript + Vite, Web Crypto API

**Design doc:** `docs/plans/2026-02-23-fxa-auth-shim-design.md`

---

## Phase 1: Backend Crypto Foundation

### Task 1: FxA Crypto Module

The FxA onepw protocol uses HKDF-SHA256 extensively. This module is the foundation for everything else. Test against FxA published test vectors.

**Files:**
- Create: `lambda/src/services/fxa_crypto.py`
- Test: `lambda/tests/services/test_fxa_crypto.py`

**Reference:** The `cryptography` library is already a dependency (used by `oidc_validator.py`). Use `cryptography.hazmat.primitives.hashes`, `cryptography.hazmat.primitives.kdf.hkdf`, and stdlib `hmac`/`hashlib`.

**Step 1: Write failing tests for HKDF key derivation**

```python
# lambda/tests/services/test_fxa_crypto.py
import pytest
from src.services.fxa_crypto import (
    derive_auth_pw,
    derive_unwrap_bkey,
    derive_verify_hash,
    derive_token_id,
    derive_req_hmac_key,
    derive_key_request_key,
    encrypt_key_bundle,
)


class TestDeriveAuthPW:
    """Test authPW derivation from quickStretchedPW."""

    def test_derive_auth_pw_from_known_input(self):
        # quickStretchedPW is 32 bytes; authPW = HKDF(qsPW, info="identity.mozilla.com/picl/v1/authPW")
        quick_stretched = bytes(32)  # all zeros for test
        result = derive_auth_pw(quick_stretched)
        assert isinstance(result, bytes)
        assert len(result) == 32

    def test_derive_auth_pw_deterministic(self):
        quick_stretched = bytes.fromhex("a" * 64)
        assert derive_auth_pw(quick_stretched) == derive_auth_pw(quick_stretched)

    def test_derive_auth_pw_differs_from_unwrap_bkey(self):
        quick_stretched = bytes.fromhex("b" * 64)
        assert derive_auth_pw(quick_stretched) != derive_unwrap_bkey(quick_stretched)


class TestDeriveVerifyHash:
    """Test verifyHash derivation from authPW."""

    def test_derive_verify_hash_length(self):
        auth_pw = bytes(32)
        result = derive_verify_hash(auth_pw)
        assert len(result) == 32

    def test_derive_verify_hash_deterministic(self):
        auth_pw = bytes.fromhex("c" * 64)
        assert derive_verify_hash(auth_pw) == derive_verify_hash(auth_pw)


class TestTokenDerivation:
    """Test sessionToken/keyFetchToken ID derivation."""

    def test_derive_session_token_id(self):
        token = bytes(32)
        token_id = derive_token_id(token, "identity.mozilla.com/picl/v1/sessionToken")
        assert len(token_id) == 32

    def test_derive_key_fetch_token_parts(self):
        token = bytes(32)
        info = "identity.mozilla.com/picl/v1/keyFetchToken"
        token_id = derive_token_id(token, info)
        hmac_key = derive_req_hmac_key(token, info)
        request_key = derive_key_request_key(token, info)
        assert len(token_id) == 32
        assert len(hmac_key) == 32
        assert len(request_key) == 32
        assert token_id != hmac_key != request_key


class TestKeyBundle:
    """Test key bundle encryption/decryption for /v1/account/keys."""

    def test_encrypt_key_bundle_length(self):
        key_request_key = bytes(32)
        k_a = bytes(32)
        wrap_kb = bytes(32)
        bundle = encrypt_key_bundle(key_request_key, k_a, wrap_kb)
        # 64 bytes ciphertext (kA + wrapKB) + 32 bytes HMAC
        assert len(bundle) == 96

    def test_encrypt_key_bundle_not_plaintext(self):
        key_request_key = bytes.fromhex("d" * 64)
        k_a = bytes.fromhex("aa" * 32)
        wrap_kb = bytes.fromhex("bb" * 32)
        bundle = encrypt_key_bundle(key_request_key, k_a, wrap_kb)
        assert bundle[:64] != k_a + wrap_kb
```

**Step 2: Run tests to verify they fail**

Run: `cd lambda && uv run pytest tests/services/test_fxa_crypto.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.fxa_crypto'`

**Step 3: Implement the crypto module**

```python
# lambda/src/services/fxa_crypto.py
import hashlib
import hmac as hmac_mod
import os

from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


NAMESPACE = "identity.mozilla.com/picl/v1/"


def _hkdf(ikm: bytes, info: str, length: int = 32) -> bytes:
    return HKDF(
        algorithm=SHA256(),
        length=length,
        salt=b"",
        info=info.encode("utf-8"),
    ).derive(ikm)


def derive_auth_pw(quick_stretched_pw: bytes) -> bytes:
    return _hkdf(quick_stretched_pw, f"{NAMESPACE}authPW")


def derive_unwrap_bkey(quick_stretched_pw: bytes) -> bytes:
    return _hkdf(quick_stretched_pw, f"{NAMESPACE}unwrapBkey")


def derive_verify_hash(auth_pw: bytes) -> bytes:
    return _hkdf(auth_pw, f"{NAMESPACE}verifyHash")


def derive_token_id(token: bytes, info: str) -> bytes:
    derived = _hkdf(token, info, length=96)
    return derived[:32]


def derive_req_hmac_key(token: bytes, info: str) -> bytes:
    derived = _hkdf(token, info, length=96)
    return derived[32:64]


def derive_key_request_key(token: bytes, info: str) -> bytes:
    derived = _hkdf(token, info, length=96)
    return derived[64:96]


def encrypt_key_bundle(key_request_key: bytes, k_a: bytes, wrap_kb: bytes) -> bytes:
    keys = _hkdf(key_request_key, f"{NAMESPACE}account/keys", length=96)
    hmac_key = keys[:32]
    xor_key = keys[32:96]
    plaintext = k_a + wrap_kb
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, xor_key))
    mac = hmac_mod.new(hmac_key, ciphertext, hashlib.sha256).digest()
    return ciphertext + mac


def generate_random_bytes(length: int = 32) -> bytes:
    return os.urandom(length)


def constant_time_compare(a: bytes, b: bytes) -> bool:
    return hmac_mod.compare_digest(a, b)
```

**Step 4: Run tests to verify they pass**

Run: `cd lambda && uv run pytest tests/services/test_fxa_crypto.py -v`
Expected: All PASS

**Step 5: Run black, isort, mypy**

Run: `cd lambda && uv run black src/services/fxa_crypto.py tests/services/test_fxa_crypto.py && uv run isort src/services/fxa_crypto.py tests/services/test_fxa_crypto.py && uv run mypy src/services/fxa_crypto.py`

**Step 6: Commit**

```bash
git add lambda/src/services/fxa_crypto.py lambda/tests/services/test_fxa_crypto.py
git commit -m "feat: add FxA crypto module for onepw key derivation"
```

---

### Task 2: Auth Account Manager

DynamoDB operations for FxA accounts: create, lookup by email, lookup by uid.

**Files:**
- Create: `lambda/src/services/auth_account_manager.py`
- Test: `lambda/tests/services/test_auth_account_manager.py`

**Reference:** Follow the existing pattern in `lambda/src/services/user_manager.py` for DynamoDB operations and `lambda/src/services/hawk_service.py` for token storage.

**Step 1: Write failing tests**

```python
# lambda/tests/services/test_auth_account_manager.py
import uuid
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from src.services.auth_account_manager import AuthAccountManager


@pytest.fixture
def mock_table():
    return MagicMock()


@pytest.fixture
def manager(mock_table):
    return AuthAccountManager(table=mock_table)


class TestCreateAccount:
    def test_create_account_stores_account_and_email_records(self, manager, mock_table):
        uid = str(uuid.uuid4())
        manager.create_account(
            uid=uid,
            email="test@example.com",
            verify_hash="aa" * 32,
            k_a="bb" * 32,
            wrap_kb="cc" * 32,
            oidc_sub="sub123",
        )
        # Should write both ACCOUNT# and EMAIL# records
        calls = mock_table.put_item.call_args_list
        assert len(calls) == 2
        pks = {call.kwargs["Item"]["PK"] for call in calls}
        assert f"ACCOUNT#{uid}" in pks
        assert "EMAIL#test@example.com" in pks

    def test_create_account_normalizes_email(self, manager, mock_table):
        manager.create_account(
            uid="uid1",
            email="Test@EXAMPLE.com",
            verify_hash="aa" * 32,
            k_a="bb" * 32,
            wrap_kb="cc" * 32,
            oidc_sub="sub123",
        )
        calls = mock_table.put_item.call_args_list
        email_record = next(c for c in calls if c.kwargs["Item"]["PK"].startswith("EMAIL#"))
        assert email_record.kwargs["Item"]["PK"] == "EMAIL#test@example.com"

    def test_create_account_rejects_duplicate_email(self, manager, mock_table):
        error = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem"
        )
        mock_table.put_item.side_effect = [None, error]  # account ok, email fails
        with pytest.raises(ValueError, match="already exists"):
            manager.create_account(
                uid="uid2", email="dup@example.com",
                verify_hash="aa" * 32, k_a="bb" * 32, wrap_kb="cc" * 32, oidc_sub="sub",
            )


class TestGetAccountByEmail:
    def test_returns_account_for_existing_email(self, manager, mock_table):
        mock_table.get_item.side_effect = [
            {"Item": {"PK": "EMAIL#test@example.com", "uid": "uid1"}},
            {"Item": {"PK": "ACCOUNT#uid1", "uid": "uid1", "email": "test@example.com",
                       "verifyHash": "aa" * 32, "kA": "bb" * 32, "wrapKB": "cc" * 32,
                       "oidcSub": "sub1", "verified": True, "createdAt": 1000}},
        ]
        account = manager.get_account_by_email("test@example.com")
        assert account is not None
        assert account["uid"] == "uid1"

    def test_returns_none_for_unknown_email(self, manager, mock_table):
        mock_table.get_item.return_value = {}
        account = manager.get_account_by_email("missing@example.com")
        assert account is None


class TestGetAccountByUid:
    def test_returns_account_for_existing_uid(self, manager, mock_table):
        mock_table.get_item.return_value = {
            "Item": {"PK": "ACCOUNT#uid1", "uid": "uid1", "email": "test@example.com",
                      "verifyHash": "aa" * 32, "kA": "bb" * 32, "wrapKB": "cc" * 32,
                      "oidcSub": "sub1", "verified": True, "createdAt": 1000}
        }
        account = manager.get_account_by_uid("uid1")
        assert account is not None
        assert account["email"] == "test@example.com"

    def test_returns_none_for_unknown_uid(self, manager, mock_table):
        mock_table.get_item.return_value = {}
        assert manager.get_account_by_uid("missing") is None
```

**Step 2: Run tests to verify they fail**

Run: `cd lambda && uv run pytest tests/services/test_auth_account_manager.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement account manager**

```python
# lambda/src/services/auth_account_manager.py
import time
from typing import Any

from botocore.exceptions import ClientError


class AuthAccountManager:
    def __init__(self, table: Any):
        self._table = table

    def create_account(
        self,
        uid: str,
        email: str,
        verify_hash: str,
        k_a: str,
        wrap_kb: str,
        oidc_sub: str,
    ) -> None:
        normalized_email = email.lower().strip()
        now = int(time.time() * 1000)

        self._table.put_item(Item={
            "PK": f"ACCOUNT#{uid}",
            "uid": uid,
            "email": normalized_email,
            "verifyHash": verify_hash,
            "kA": k_a,
            "wrapKB": wrap_kb,
            "oidcSub": oidc_sub,
            "verified": True,
            "createdAt": now,
        })

        try:
            self._table.put_item(
                Item={"PK": f"EMAIL#{normalized_email}", "uid": uid},
                ConditionExpression="attribute_not_exists(PK)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ValueError(f"Account with email {normalized_email} already exists")
            raise

    def get_account_by_email(self, email: str) -> dict | None:
        normalized = email.lower().strip()
        resp = self._table.get_item(Key={"PK": f"EMAIL#{normalized}"})
        email_record = resp.get("Item")
        if not email_record:
            return None
        return self.get_account_by_uid(email_record["uid"])

    def get_account_by_uid(self, uid: str) -> dict | None:
        resp = self._table.get_item(Key={"PK": f"ACCOUNT#{uid}"})
        return resp.get("Item")
```

**Step 4: Run tests, linters**

Run: `cd lambda && uv run pytest tests/services/test_auth_account_manager.py -v`
Run: `cd lambda && uv run black src/services/auth_account_manager.py tests/services/test_auth_account_manager.py && uv run isort src/services/auth_account_manager.py tests/services/test_auth_account_manager.py && uv run mypy src/services/auth_account_manager.py`

**Step 5: Commit**

```bash
git add lambda/src/services/auth_account_manager.py lambda/tests/services/test_auth_account_manager.py
git commit -m "feat: add auth account manager for FxA account storage"
```

---

### Task 3: FxA Token Manager

Manages session tokens and key-fetch tokens in DynamoDB: create, verify, consume.

**Files:**
- Create: `lambda/src/services/fxa_token_manager.py`
- Test: `lambda/tests/services/test_fxa_token_manager.py`

**Reference:** Follow `lambda/src/services/hawk_service.py` for DynamoDB token storage with TTL.

**Step 1: Write failing tests**

```python
# lambda/tests/services/test_fxa_token_manager.py
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from src.services.fxa_token_manager import FxATokenManager


SESSION_TOKEN_INFO = "identity.mozilla.com/picl/v1/sessionToken"
KEY_FETCH_TOKEN_INFO = "identity.mozilla.com/picl/v1/keyFetchToken"


@pytest.fixture
def mock_table():
    return MagicMock()


@pytest.fixture
def manager(mock_table):
    return FxATokenManager(table=mock_table, session_ttl_seconds=2592000, keyfetch_ttl_seconds=300)


class TestCreateSessionToken:
    def test_returns_raw_token(self, manager):
        raw_token = manager.create_session_token("uid1")
        assert isinstance(raw_token, bytes)
        assert len(raw_token) == 32

    def test_stores_session_in_dynamo(self, manager, mock_table):
        manager.create_session_token("uid1")
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args.kwargs["Item"]
        assert item["PK"].startswith("SESSION#")
        assert item["uid"] == "uid1"
        assert "expiry" in item


class TestVerifySessionToken:
    def test_returns_uid_for_valid_token(self, manager, mock_table):
        raw_token = manager.create_session_token("uid1")
        token_id_hex = mock_table.put_item.call_args.kwargs["Item"]["PK"].split("#")[1]
        mock_table.get_item.return_value = {
            "Item": {"PK": f"SESSION#{token_id_hex}", "uid": "uid1", "verified": True}
        }
        uid = manager.verify_session_token_id(token_id_hex)
        assert uid == "uid1"

    def test_returns_none_for_unknown_token(self, manager, mock_table):
        mock_table.get_item.return_value = {}
        assert manager.verify_session_token_id("nonexistent") is None


class TestCreateKeyFetchToken:
    def test_returns_raw_token(self, manager):
        raw_token = manager.create_key_fetch_token("uid1")
        assert isinstance(raw_token, bytes)
        assert len(raw_token) == 32

    def test_stores_keyfetch_in_dynamo(self, manager, mock_table):
        manager.create_key_fetch_token("uid1")
        item = mock_table.put_item.call_args.kwargs["Item"]
        assert item["PK"].startswith("KEYFETCH#")
        assert "keyFetchToken" in item


class TestConsumeKeyFetchToken:
    def test_returns_raw_token_and_uid_then_deletes(self, manager, mock_table):
        token_id_hex = "aa" * 32
        mock_table.get_item.return_value = {
            "Item": {"PK": f"KEYFETCH#{token_id_hex}", "uid": "uid1",
                     "keyFetchToken": "bb" * 32}
        }
        result = manager.consume_key_fetch_token(token_id_hex)
        assert result is not None
        assert result["uid"] == "uid1"
        mock_table.delete_item.assert_called_once()

    def test_returns_none_for_unknown_token(self, manager, mock_table):
        mock_table.get_item.return_value = {}
        assert manager.consume_key_fetch_token("missing") is None
```

**Step 2: Run tests to verify failure, implement, run again, lint, commit**

Run: `cd lambda && uv run pytest tests/services/test_fxa_token_manager.py -v`

Implementation in `lambda/src/services/fxa_token_manager.py`:
- `create_session_token(uid) -> bytes` — generates random 32 bytes, derives tokenId via HKDF, stores SESSION# record with TTL
- `verify_session_token_id(token_id_hex) -> str | None` — looks up SESSION# record, returns uid
- `create_key_fetch_token(uid) -> bytes` — generates random 32 bytes, derives tokenId, stores KEYFETCH# record with raw token and short TTL
- `consume_key_fetch_token(token_id_hex) -> dict | None` — looks up KEYFETCH#, returns item, deletes it (single-use)
- `delete_session(token_id_hex) -> None` — deletes SESSION# record

Uses `fxa_crypto.derive_token_id()` for token ID derivation.

**Step 3: Commit**

```bash
git add lambda/src/services/fxa_token_manager.py lambda/tests/services/test_fxa_token_manager.py
git commit -m "feat: add FxA token manager for session and key-fetch tokens"
```

---

### Task 4: JWT Service (KMS Signing)

Signs OAuth JWTs using KMS and provides the public key for JWKS.

**Files:**
- Create: `lambda/src/services/jwt_service.py`
- Test: `lambda/tests/services/test_jwt_service.py`

**Reference:** The `cryptography` library is already available. Use `boto3` KMS client for signing.

**Step 1: Write failing tests**

```python
# lambda/tests/services/test_jwt_service.py
import base64
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from src.services.jwt_service import JWTService


@pytest.fixture
def mock_kms():
    client = MagicMock()
    # Mock GetPublicKey response with a dummy DER-encoded RSA public key
    # In real tests, use a generated key pair for round-trip testing
    client.get_public_key.return_value = {
        "PublicKey": b"\x00" * 294,  # placeholder
        "KeyId": "key-123",
        "KeySpec": "RSA_2048",
        "SigningAlgorithms": ["RSASSA_PKCS1_V1_5_SHA_256"],
    }
    client.sign.return_value = {
        "Signature": b"\x00" * 256,
        "SigningAlgorithm": "RSASSA_PKCS1_V1_5_SHA_256",
    }
    return client


@pytest.fixture
def service(mock_kms):
    return JWTService(
        kms_client=mock_kms,
        signing_key_id="key-123",
        issuer="https://auth.prod.ffsync.layertwo.dev",
    )


class TestSignJWT:
    def test_returns_three_part_jwt(self, service):
        token = service.sign_jwt(sub="user1", scope="https://identity.mozilla.com/apps/oldsync", ttl=300)
        parts = token.split(".")
        assert len(parts) == 3

    def test_header_specifies_rs256(self, service):
        token = service.sign_jwt(sub="user1", scope="openid", ttl=300)
        header = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))
        assert header["alg"] == "RS256"
        assert header["typ"] == "JWT"

    def test_payload_contains_claims(self, service):
        token = service.sign_jwt(sub="user1", scope="openid", ttl=300)
        payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        assert payload["sub"] == "user1"
        assert payload["iss"] == "https://auth.prod.ffsync.layertwo.dev"
        assert "exp" in payload
        assert "iat" in payload

    def test_calls_kms_sign(self, service, mock_kms):
        service.sign_jwt(sub="user1", scope="openid", ttl=300)
        mock_kms.sign.assert_called_once()
        call_kwargs = mock_kms.sign.call_args.kwargs
        assert call_kwargs["KeyId"] == "key-123"
        assert call_kwargs["SigningAlgorithm"] == "RSASSA_PKCS1_V1_5_SHA_256"
```

**Step 2: Implement, test, lint, commit**

Implementation in `lambda/src/services/jwt_service.py`:
- `sign_jwt(sub, scope, ttl, client_id=None) -> str` — builds header+payload, calls `kms.sign()`, returns JWT string
- `get_public_key_jwk() -> dict` — calls `kms.get_public_key()`, converts DER to JWK format, caches in memory
- `verify_jwt(token) -> dict` — decodes JWT, verifies signature using cached public key via `cryptography` RSA verification (no KMS call needed for verification)

```bash
git add lambda/src/services/jwt_service.py lambda/tests/services/test_jwt_service.py
git commit -m "feat: add JWT service with KMS signing for OAuth tokens"
```

---

### Task 5: OAuth Code Manager

Manages OAuth authorization codes and refresh tokens in DynamoDB.

**Files:**
- Create: `lambda/src/services/oauth_code_manager.py`
- Test: `lambda/tests/services/test_oauth_code_manager.py`

**Step 1: Write failing tests**

Tests cover:
- `create_authorization_code(uid, client_id, scope, code_challenge, code_challenge_method) -> str` — stores OAUTHCODE# with TTL, returns code
- `consume_authorization_code(code) -> dict | None` — retrieves and deletes (single-use)
- `create_refresh_token(uid, client_id, scope) -> str` — stores REFRESH# with TTL
- `consume_refresh_token(token_hash) -> dict | None` — retrieves and deletes
- PKCE validation: `verify_code_challenge(verifier, challenge, method) -> bool`

**Step 2: Implement, test, lint, commit**

```bash
git add lambda/src/services/oauth_code_manager.py lambda/tests/services/test_oauth_code_manager.py
git commit -m "feat: add OAuth code manager for authorization codes and refresh tokens"
```

---

## Phase 2: Account Routes

### Task 6: AccountStatus Route

Simplest route — good starting point. No auth required.

**Files:**
- Create: `lambda/src/routes/auth/account_status.py`
- Test: `lambda/tests/routes/auth/test_account_status.py`

**Reference:** Follow the pattern in `lambda/src/routes/token/request.py` — extend `BaseRoute`, implement `bind()` and `handle()`.

**Step 1: Write failing tests**

```python
# lambda/tests/routes/auth/test_account_status.py
import json
from unittest.mock import MagicMock

import pytest

from src.routes.auth.account_status import AccountStatusRoute


@pytest.fixture
def mock_account_manager():
    return MagicMock()


@pytest.fixture
def route(mock_account_manager):
    return AccountStatusRoute(account_manager=mock_account_manager)


class TestAccountStatus:
    def test_returns_true_for_existing_account(self, route, mock_account_manager):
        mock_account_manager.get_account_by_email.return_value = {"uid": "uid1"}
        event = {"httpMethod": "GET", "path": "/v1/account/status",
                 "queryStringParameters": {"email": "test@example.com"},
                 "headers": {}, "requestContext": {}}
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["exists"] is True

    def test_returns_false_for_unknown_account(self, route, mock_account_manager):
        mock_account_manager.get_account_by_email.return_value = None
        event = {"httpMethod": "GET", "path": "/v1/account/status",
                 "queryStringParameters": {"email": "missing@example.com"},
                 "headers": {}, "requestContext": {}}
        response = route.handle(event)
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["exists"] is False

    def test_returns_400_for_missing_email(self, route):
        event = {"httpMethod": "GET", "path": "/v1/account/status",
                 "queryStringParameters": {}, "headers": {}, "requestContext": {}}
        response = route.handle(event)
        assert response.status_code == 400
```

**Step 2: Implement, test, lint, commit**

```bash
git add lambda/src/routes/auth/__init__.py lambda/src/routes/auth/account_status.py \
  lambda/tests/routes/auth/__init__.py lambda/tests/routes/auth/test_account_status.py
git commit -m "feat: add AccountStatus route (GET /v1/account/status)"
```

---

### Task 7: AccountCreate Route

Creates FxA account. Requires OIDC Bearer token to link identity.

**Files:**
- Create: `lambda/src/routes/auth/account_create.py`
- Test: `lambda/tests/routes/auth/test_account_create.py`

**Step 1: Write failing tests**

Tests cover:
- Valid request with email + authPW + OIDC Bearer → 200 with uid, sessionToken, keyFetchToken
- Missing Authorization header → 401
- Invalid OIDC token → 401
- Duplicate email → 409
- Missing email or authPW in body → 400

**Step 2: Implement**

`AccountCreate.handle()`:
1. Extract and validate OIDC Bearer token via `OIDCValidator` → get `sub`
2. Parse JSON body for `email`, `authPW`
3. Generate uid (UUID4)
4. Derive verifyHash from authPW
5. Generate random kA, wrapKB
6. Call `account_manager.create_account()`
7. Create session token and key-fetch token via `token_manager`
8. Return JSON with `uid`, `sessionToken` (hex), `keyFetchToken` (hex), `verified: true`

**Step 3: Test, lint, commit**

```bash
git add lambda/src/routes/auth/account_create.py lambda/tests/routes/auth/test_account_create.py
git commit -m "feat: add AccountCreate route (POST /v1/account/create)"
```

---

### Task 8: AccountLogin Route

Verifies authPW, issues tokens. No OIDC needed — password-only.

**Files:**
- Create: `lambda/src/routes/auth/account_login.py`
- Test: `lambda/tests/routes/auth/test_account_login.py`

**Step 1: Write failing tests**

Tests cover:
- Valid email + authPW → 200 with uid, sessionToken, keyFetchToken, verified
- Unknown email → 400 (errno 102 "Unknown account")
- Incorrect authPW → 400 (errno 103 "Incorrect password")
- Missing body fields → 400
- `keys=true` query param returns keyFetchToken, `keys=false` omits it

**Step 2: Implement**

`AccountLogin.handle()`:
1. Parse JSON body for `email`, `authPW`
2. Look up account by email
3. Derive verifyHash from authPW, constant-time compare
4. Create sessionToken (always) and keyFetchToken (if `keys=true`)
5. Return response matching FxA format

**Step 3: Test, lint, commit**

```bash
git add lambda/src/routes/auth/account_login.py lambda/tests/routes/auth/test_account_login.py
git commit -m "feat: add AccountLogin route (POST /v1/account/login)"
```

---

### Task 9: AccountKeys Route

Returns encrypted kA + wrapKB bundle. Single-use keyFetchToken auth.

**Files:**
- Create: `lambda/src/routes/auth/account_keys.py`
- Test: `lambda/tests/routes/auth/test_account_keys.py`

**Step 1: Write failing tests**

Tests cover:
- Valid keyFetchToken → 200 with `bundle` (hex-encoded encrypted kA + wrapKB)
- Token consumed — second request with same token → 401
- Invalid/missing authorization → 401

**Step 2: Implement**

`AccountKeys.handle()`:
1. Parse Hawk-style Authorization header to extract tokenId
2. Consume keyFetchToken from DynamoDB (single-use)
3. Look up account by uid
4. Derive keyRequestKey from raw keyFetchToken
5. Encrypt key bundle (kA + wrapKB) using keyRequestKey
6. Return `{"bundle": hex(encrypted_bundle)}`

**Step 3: Test, lint, commit**

```bash
git add lambda/src/routes/auth/account_keys.py lambda/tests/routes/auth/test_account_keys.py
git commit -m "feat: add AccountKeys route (GET /v1/account/keys)"
```

---

### Task 10: AccountProfile Route

Returns basic profile info. Session token or OAuth Bearer auth.

**Files:**
- Create: `lambda/src/routes/auth/account_profile.py`
- Test: `lambda/tests/routes/auth/test_account_profile.py`

**Step 1: Write tests, implement, commit**

Returns `{"email": "...", "uid": "...", "locale": "en-US"}`. Authenticate via session token ID lookup or OAuth Bearer JWT verification.

```bash
git add lambda/src/routes/auth/account_profile.py lambda/tests/routes/auth/test_account_profile.py
git commit -m "feat: add AccountProfile route (GET /v1/account/profile)"
```

---

### Task 11: ScopedKeyData Route

Returns key metadata Firefox needs for sync encryption key derivation.

**Files:**
- Create: `lambda/src/routes/auth/scoped_key_data.py`
- Test: `lambda/tests/routes/auth/test_scoped_key_data.py`

**Step 1: Write tests, implement, commit**

Request body: `{"client_id": "...", "scope": "https://identity.mozilla.com/apps/oldsync"}`
Response:
```json
{
  "https://identity.mozilla.com/apps/oldsync": {
    "identifier": "https://identity.mozilla.com/apps/oldsync",
    "keyRotationSecret": "0000000000000000000000000000000000000000000000000000000000000000",
    "keyRotationTimestamp": 1234567890
  }
}
```

`keyRotationTimestamp` is the account's `createdAt` value. `keyRotationSecret` is a fixed 32-byte zero hex for initial deployment (key rotation not needed initially).

```bash
git add lambda/src/routes/auth/scoped_key_data.py lambda/tests/routes/auth/test_scoped_key_data.py
git commit -m "feat: add ScopedKeyData route (POST /v1/account/scoped-key-data)"
```

---

## Phase 3: Session Routes

### Task 12: SessionStatus and SessionDestroy Routes

**Files:**
- Create: `lambda/src/routes/auth/session_status.py`
- Create: `lambda/src/routes/auth/session_destroy.py`
- Test: `lambda/tests/routes/auth/test_session_status.py`
- Test: `lambda/tests/routes/auth/test_session_destroy.py`

**SessionStatus** (GET /v1/session/status):
- Authenticate via session token Hawk header
- Return `{"state": "verified", "uid": "..."}` or 401

**SessionDestroy** (POST /v1/session/destroy):
- Authenticate via session token Hawk header
- Delete session from DynamoDB
- Return 200 `{}`

```bash
git add lambda/src/routes/auth/session_status.py lambda/src/routes/auth/session_destroy.py \
  lambda/tests/routes/auth/test_session_status.py lambda/tests/routes/auth/test_session_destroy.py
git commit -m "feat: add SessionStatus and SessionDestroy routes"
```

---

## Phase 4: OAuth Routes

### Task 13: OAuthAuthorization Route

Issues OAuth authorization codes.

**Files:**
- Create: `lambda/src/routes/auth/oauth_authorization.py`
- Test: `lambda/tests/routes/auth/test_oauth_authorization.py`

**Step 1: Write tests, implement**

Request: authenticated with sessionToken. Body: `{"client_id": "...", "scope": "...", "state": "...", "code_challenge": "...", "code_challenge_method": "S256"}`
Response: `{"code": "...", "state": "...", "redirect": "urn:ietf:wg:oauth:2.0:oob"}`

```bash
git add lambda/src/routes/auth/oauth_authorization.py lambda/tests/routes/auth/test_oauth_authorization.py
git commit -m "feat: add OAuthAuthorization route (POST /v1/oauth/authorization)"
```

---

### Task 14: OAuthToken Route

Exchanges authorization code or refresh token for JWT access token.

**Files:**
- Create: `lambda/src/routes/auth/oauth_token.py`
- Test: `lambda/tests/routes/auth/test_oauth_token.py`

**Step 1: Write tests**

Tests cover:
- `grant_type=authorization_code` with valid code + PKCE verifier → 200 with access_token JWT, refresh_token, token_type, expires_in, scope
- Invalid code → 400
- Invalid PKCE verifier → 400
- `grant_type=refresh_token` with valid refresh token → 200 with new access_token
- Invalid refresh token → 400
- Missing grant_type → 400

**Step 2: Implement**

`OAuthToken.handle()`:
1. Parse body for `grant_type`
2. If `authorization_code`: consume code, verify PKCE, sign JWT via `jwt_service.sign_jwt()`, create refresh token
3. If `refresh_token`: consume refresh token, sign new JWT, create new refresh token
4. Return token response

The `sub` claim in the JWT is set to the account's `oidcSub` — this is what the Token Server uses to look up the user in the token-users table.

```bash
git add lambda/src/routes/auth/oauth_token.py lambda/tests/routes/auth/test_oauth_token.py
git commit -m "feat: add OAuthToken route (POST /v1/oauth/token)"
```

---

### Task 15: OAuthDestroy Route

Revokes tokens.

**Files:**
- Create: `lambda/src/routes/auth/oauth_destroy.py`
- Test: `lambda/tests/routes/auth/test_oauth_destroy.py`

Simple endpoint. Accepts `{"token": "..."}` in body. Look up and delete the refresh token if it exists. Return 200 `{}` regardless (per RFC 7009 — revocation of invalid tokens is not an error).

```bash
git add lambda/src/routes/auth/oauth_destroy.py lambda/tests/routes/auth/test_oauth_destroy.py
git commit -m "feat: add OAuthDestroy route (POST /v1/oauth/destroy)"
```

---

## Phase 5: Discovery Routes

### Task 16: OIDC Discovery and JWKS Routes

**Files:**
- Create: `lambda/src/routes/auth/oidc_discovery.py`
- Create: `lambda/src/routes/auth/jwks.py`
- Test: `lambda/tests/routes/auth/test_oidc_discovery.py`
- Test: `lambda/tests/routes/auth/test_jwks.py`

**OIDC Discovery** (GET /.well-known/openid-configuration):
```json
{
  "issuer": "https://auth.prod.ffsync.layertwo.dev",
  "authorization_endpoint": "https://auth.prod.ffsync.layertwo.dev/v1/oauth/authorization",
  "token_endpoint": "https://auth.prod.ffsync.layertwo.dev/v1/oauth/token",
  "jwks_uri": "https://auth.prod.ffsync.layertwo.dev/v1/jwks",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
```

Constructed from `BASE_DOMAIN` and `STAGE` environment variables.

**JWKS** (GET /v1/jwks):
Calls `jwt_service.get_public_key_jwk()` and returns `{"keys": [jwk]}`.

```bash
git add lambda/src/routes/auth/oidc_discovery.py lambda/src/routes/auth/jwks.py \
  lambda/tests/routes/auth/test_oidc_discovery.py lambda/tests/routes/auth/test_jwks.py
git commit -m "feat: add OIDC discovery and JWKS routes"
```

---

## Phase 6: Integration Wiring

### Task 17: JWT Verifier for Token Endpoint

Replace `OIDCValidator` usage in the token endpoint with a `JWTVerifier` that validates self-issued JWTs against the KMS public key.

**Files:**
- Create: `lambda/src/services/jwt_verifier.py`
- Test: `lambda/tests/services/test_jwt_verifier.py`
- Modify: `lambda/src/routes/token/request.py` — use JWTVerifier instead of OIDCValidator

**Step 1: Write tests for JWTVerifier**

Tests cover:
- Valid JWT signed by known key → returns claims dict with `sub`, `iss`, `exp`
- Expired JWT → raises exception
- Invalid signature → raises exception
- Missing required claims → raises exception

**Step 2: Implement JWTVerifier**

Uses `jwt_service.get_public_key_jwk()` to get the public key, then validates using `PyJWT` (already a dependency via `OIDCValidator`). Does NOT call KMS for verification — uses cached public key.

**Step 3: Update GetTokenRoute**

Modify `lambda/src/routes/token/request.py` to accept either `OIDCValidator` or `JWTVerifier` for token validation. The `ServiceProvider` will wire in the `JWTVerifier`.

```bash
git add lambda/src/services/jwt_verifier.py lambda/tests/services/test_jwt_verifier.py \
  lambda/src/routes/token/request.py
git commit -m "feat: add JWT verifier for self-issued token validation"
```

---

### Task 18: Wire Routes into ServiceProvider and Entrypoint

Register all new routes in the existing router.

**Files:**
- Modify: `lambda/src/environment/service_provider.py` — add auth services and routes
- Modify: `lambda/src/entrypoint/__init__.py` — export auth handler if separate, or update token handler

**Step 1: Update ServiceProvider**

Add cached properties:
- `auth_table` — DynamoDB table from `AUTH_TABLE_NAME`
- `auth_account_manager` — `AuthAccountManager(table=self.auth_table)`
- `fxa_token_manager` — `FxATokenManager(table=self.auth_table, ...)`
- `jwt_service` — `JWTService(kms_client=..., signing_key_id=AUTH_SIGNING_KEY_ID, issuer=...)`
- `oauth_code_manager` — `OAuthCodeManager(table=self.auth_table, ...)`
- `jwt_verifier` — `JWTVerifier(jwt_service=self.jwt_service)`

Update `token_api_router` (renamed to `auth_api_router`):
- Add all new routes to the routes list
- Keep existing `GetTokenRoute` but inject `jwt_verifier` instead of `oidc_validator`

**Step 2: Update entrypoint**

Rename `token_api_handler` to `auth_api_handler` in `lambda/src/entrypoint/__init__.py` and `lambda/src/entrypoint/token_api.py` (or rename the file to `auth_api.py`).

**Step 3: Run full test suite**

Run: `cd lambda && uv run pytest tests/ -x -q`
Expected: All tests pass including existing token route tests.

```bash
git add lambda/src/environment/service_provider.py lambda/src/entrypoint/__init__.py \
  lambda/src/entrypoint/token_api.py
git commit -m "feat: wire FxA auth routes into service provider and entrypoint"
```

---

## Phase 7: CDK Infrastructure

### Task 19: Service Rename TOKEN to AUTH

**Files:**
- Modify: `lib/config/service.ts` — rename enum value
- Modify: `lib/stacks/service.ts` — rename properties and methods
- Modify: `lib/stacks/frontend.ts` — update props
- Modify: `lib/app.ts` — update cross-stack references

**Step 1: Update Service enum**

```typescript
// lib/config/service.ts
export enum Service {
    AUTH = "auth",
    STORAGE = "storage",
}
```

**Step 2: Update ServiceStack**

In `lib/stacks/service.ts`:
- Rename `tokenApiDomain` → `authApiDomain`
- Rename `tokenHandler` → `authHandler`
- Rename `tokenApi` → `authApi`
- Rename `tokenUsersTable` stays (it's still the token users table)
- Update `buildApi(Service.TOKEN, ...)` → `buildApi(Service.AUTH, ...)`
- Update Lambda function name to `ffsync-auth-api-{stage}`
- Update handler reference to `auth_api_handler`

**Step 3: Update FrontendStack**

In `lib/stacks/frontend.ts`:
- Props: `tokenApiDomain` → `authApiDomain`
- `config.json`: `tokenServerUrl` → `authServerUrl`

**Step 4: Update app.ts**

Pass `serviceStack.authApiDomain` instead of `serviceStack.tokenApiDomain`.

**Step 5: Run TypeScript compile check**

Run: `npx tsc --noEmit`

**Step 6: Commit**

```bash
git add lib/config/service.ts lib/stacks/service.ts lib/stacks/frontend.ts lib/app.ts
git commit -m "refactor: rename Service.TOKEN to Service.AUTH"
```

---

### Task 20: Smithy Model — AuthService with Resources

**Files:**
- Modify: `smithy/models/main.smithy` — rename TokenService to AuthService, add resources
- Create: `smithy/models/auth/account.smithy` — Account resource and operations
- Create: `smithy/models/auth/session.smithy` — Session resource and operations
- Create: `smithy/models/auth/oauth.smithy` — OAuth resource and operations
- Create: `smithy/models/auth/discovery.smithy` — OIDC discovery and JWKS operations

**Step 1: Create Smithy model files**

Follow patterns from `smithy/models/storage/storage.smithy` and `smithy/models/storage/collection.smithy`.

`main.smithy` — AuthService definition:
```smithy
@cors(
    origin: "CDK_CORS_ORIGIN"
    additionalAllowedHeaders: ["Authorization", "Content-Type", "X-Client-State"]
)
@restJson1
@integration(
    type: "aws_proxy"
    uri: "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/CDK_LAMBDA_FUNCTION_ARN/invocations"
    httpMethod: "POST"
    credentials: "CDK_API_ROLE_ARN"
    timeoutInMillis: 29000
)
@requestValidator("full")
service AuthService {
    version: "1.0"
    resources: [Account, Session, OAuth]
    operations: [GetToken, OIDCDiscovery, JWKS]
    errors: [AuthenticationException, ValidationException]
}
```

**Step 2: Build Smithy models**

Run: `cd smithy && ./gradlew clean build`

Verify the generated OpenAPI spec at `build/smithy/auth/openapi/AuthService.openapi.json` contains all expected paths.

**Step 3: Update CDK to read new spec path**

Update `buildOpenApiSpec` in `service.ts` to reference the new `AuthService` spec file.

**Step 4: Commit**

```bash
git add smithy/models/main.smithy smithy/models/auth/
git commit -m "feat: add AuthService Smithy model with Account, Session, OAuth resources"
```

---

### Task 21: Add DynamoDB Table and KMS Key to ServiceStack

**Files:**
- Modify: `lib/stacks/service.ts` — add auth table, KMS key, Lambda env vars, grants

**Step 1: Add auth table**

```typescript
this.authTable = new Table(this, "AuthTable", {
    tableName: `ffsync-auth-${this.props.stageType.toLowerCase()}`,
    partitionKey: { name: "PK", type: AttributeType.STRING },
    billingMode: BillingMode.PAY_PER_REQUEST,
    encryption: TableEncryption.AWS_MANAGED,
    timeToLiveAttribute: "expiry",
    pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
    removalPolicy: RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE,
});
```

**Step 2: Add KMS signing key**

```typescript
import * as kms from "aws-cdk-lib/aws-kms";

this.signingKey = new kms.Key(this, "AuthSigningKey", {
    alias: `ffsync-auth-signing-${this.props.stageType.toLowerCase()}`,
    keySpec: kms.KeySpec.RSA_2048,
    keyUsage: kms.KeyUsage.SIGN_VERIFY,
    description: "Signs OAuth JWTs for the FxA auth server",
});
```

**Step 3: Update Lambda handler**

Add environment variables `AUTH_TABLE_NAME` and `AUTH_SIGNING_KEY_ID`.
Add grants: `authTable.grantReadWriteData(handler)`, `signingKey.grantSign(handler)`, `signingKey.grant(handler, "kms:GetPublicKey")`.

**Step 4: TypeScript compile check**

Run: `npx tsc --noEmit`

**Step 5: Commit**

```bash
git add lib/stacks/service.ts
git commit -m "feat: add auth DynamoDB table and KMS signing key to ServiceStack"
```

---

### Task 22: Update FrontendStack — fxa-client-configuration

**Files:**
- Modify: `lib/stacks/frontend.ts` — add fxa-client-configuration to BucketDeployment

**Step 1: Add static discovery file**

Add to BucketDeployment sources:
```typescript
Source.jsonData(".well-known/fxa-client-configuration", {
    auth_server_base_url: `https://${this.props.authApiDomain}`,
    oauth_server_base_url: `https://${this.props.authApiDomain}`,
    profile_server_base_url: `https://${this.props.authApiDomain}`,
    sync_tokenserver_base_url: `https://${this.props.authApiDomain}`,
}),
```

**Step 2: Update config.json**

Replace `tokenServerUrl` with `authServerUrl`:
```typescript
Source.jsonData("config.json", {
    oidcProviderUrl: this.props.oidcProviderUrl.stringValue,
    clientId: this.props.clientId.stringValue,
    redirectUri: `https://${this.domainName}`,
    authServerUrl: `https://${this.props.authApiDomain}`,
    scopes: ["openid", "profile", "email"],
}),
```

**Step 3: Commit**

```bash
git add lib/stacks/frontend.ts
git commit -m "feat: add fxa-client-configuration and update config.json in FrontendStack"
```

---

## Phase 8: Frontend

### Task 23: FxA Crypto Module (TypeScript)

Client-side password stretching using Web Crypto API.

**Files:**
- Create: `frontend/src/lib/fxa-crypto.ts`

**Step 1: Implement**

```typescript
// frontend/src/lib/fxa-crypto.ts
const NAMESPACE = "identity.mozilla.com/picl/v1/"

function encode(str: string): Uint8Array {
  return new TextEncoder().encode(str)
}

function toHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
}

async function hkdf(
  ikm: ArrayBuffer, info: string, length: number = 32
): Promise<ArrayBuffer> {
  const key = await crypto.subtle.importKey("raw", ikm, "HKDF", false, ["deriveBits"])
  return crypto.subtle.deriveBits(
    { name: "HKDF", hash: "SHA-256", salt: new Uint8Array(0), info: encode(info) },
    key, length * 8
  )
}

export async function stretchPassword(
  email: string, password: string
): Promise<{ authPW: string; unwrapBKey: string }> {
  const salt = encode(`${NAMESPACE}quickStretch:${email}`)
  const passwordBytes = encode(password)

  const baseKey = await crypto.subtle.importKey("raw", passwordBytes, "PBKDF2", false, ["deriveBits"])
  const quickStretched = await crypto.subtle.deriveBits(
    { name: "PBKDF2", salt, iterations: 1000, hash: "SHA-256" }, baseKey, 256
  )

  const authPW = await hkdf(quickStretched, `${NAMESPACE}authPW`)
  const unwrapBKey = await hkdf(quickStretched, `${NAMESPACE}unwrapBkey`)

  return { authPW: toHex(authPW), unwrapBKey: toHex(unwrapBKey) }
}
```

**Step 2: Lint**

Run: `cd frontend && npm run lint`

**Step 3: Commit**

```bash
git add frontend/src/lib/fxa-crypto.ts
git commit -m "feat: add FxA client-side password stretching via Web Crypto API"
```

---

### Task 24: WebChannel Module

Communication with Firefox via WebChannel events.

**Files:**
- Create: `frontend/src/lib/webchannel.ts`

**Step 1: Implement**

```typescript
// frontend/src/lib/webchannel.ts
const FXA_WEBCHANNEL_ID = "account_updates"

interface WebChannelMessage {
  id: string
  message: {
    command: string
    data: Record<string, unknown>
    messageId?: string
  }
}

export function sendToFirefox(command: string, data: Record<string, unknown>): void {
  const detail: WebChannelMessage = {
    id: FXA_WEBCHANNEL_ID,
    message: { command, data },
  }
  window.dispatchEvent(
    new CustomEvent("WebChannelMessageToChrome", {
      detail: JSON.stringify(detail),
    })
  )
}

export function listenFromFirefox(
  callback: (command: string, data: Record<string, unknown>, messageId?: string) => void
): () => void {
  const handler = (event: Event) => {
    const detail = JSON.parse((event as CustomEvent).detail)
    const { command, data, messageId } = detail.message
    callback(command, data, messageId)
  }
  window.addEventListener("WebChannelMessageToContent", handler)
  return () => window.removeEventListener("WebChannelMessageToContent", handler)
}

export function sendOAuthLogin(
  code: string, state: string, declinedSyncEngines: string[] = []
): void {
  sendToFirefox("fxaccounts:oauth_login", {
    code,
    state,
    redirect: "urn:ietf:wg:oauth:2.0:oob",
    declinedSyncEngines,
  })
}
```

**Step 2: Commit**

```bash
git add frontend/src/lib/webchannel.ts
git commit -m "feat: add WebChannel module for Firefox communication"
```

---

### Task 25: Auth Client Module

HTTP client for the auth server API.

**Files:**
- Create: `frontend/src/lib/auth-client.ts`

**Step 1: Implement**

Functions:
- `checkAccountStatus(authServerUrl, email) -> { exists: boolean }`
- `createAccount(authServerUrl, email, authPW, oidcToken) -> { uid, sessionToken, keyFetchToken }`
- `login(authServerUrl, email, authPW) -> { uid, sessionToken, keyFetchToken }`
- `requestOAuthCode(authServerUrl, sessionToken, clientId, scope, state, codeChallenge) -> { code, state }`

Each function calls the corresponding auth server endpoint with proper headers and body.

**Step 2: Commit**

```bash
git add frontend/src/lib/auth-client.ts
git commit -m "feat: add auth server HTTP client"
```

---

### Task 26: React Router and FxA Sign-In Pages

Add routing and the WebChannel-based sign-in flow.

**Files:**
- Modify: `frontend/package.json` — add react-router dependency
- Modify: `frontend/src/main.tsx` — wrap App in BrowserRouter
- Modify: `frontend/src/App.tsx` — add routes
- Create: `frontend/src/components/SignInPage.tsx`
- Create: `frontend/src/components/SignUpPage.tsx`
- Create: `frontend/src/components/SyncPasswordForm.tsx`
- Modify: `frontend/src/lib/types.ts` — add authServerUrl to AppConfig

**Step 1: Install react-router**

Run: `cd frontend && npm install react-router`

**Step 2: Update types**

Add `authServerUrl` to `AppConfig`, remove `tokenServerUrl`.

**Step 3: Add routing in App.tsx**

Detect FxA context (`context=oauth_webchannel_v1` in URL search params). If present, render FxA sign-in flow. Otherwise, render existing manual flow.

**Step 4: Create SignInPage**

Flow:
1. Listen for `fxaccounts:fxa_status` WebChannel message from Firefox
2. Respond with capabilities
3. Show OIDC login button (reuse existing flow)
4. After OIDC auth, show SyncPasswordForm
5. Call `stretchPassword()` from `fxa-crypto.ts`
6. Call `login()` or `createAccount()` from `auth-client.ts`
7. Call `requestOAuthCode()` from `auth-client.ts`
8. Send `fxaccounts:oauth_login` via WebChannel with code, state, unwrapBKey

**Step 5: Create SyncPasswordForm**

Form with email (pre-filled from OIDC) and sync password inputs. Submit calls parent callback.

**Step 6: Build and lint**

Run: `cd frontend && npm run build && npm run lint`

**Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/
git commit -m "feat: add FxA sign-in pages with WebChannel integration"
```

---

## Phase 9: Final Integration

### Task 27: Update Frontend Config Loader

**Files:**
- Modify: `frontend/src/lib/config.ts` — handle `authServerUrl` field
- Modify: `frontend/src/lib/token-server.ts` — update if needed or deprecate

Update `loadConfig()` to accept `authServerUrl`. The `tokenServerUrl` field becomes optional (backwards compatibility during transition).

```bash
git add frontend/src/lib/config.ts frontend/src/lib/token-server.ts
git commit -m "refactor: update config loader for authServerUrl"
```

---

### Task 28: End-to-End Integration Test

**Files:**
- Create: `tools/fxa_integration_test.py`

Script that exercises the full chain:
1. Derive authPW + unwrapBKey from test email + password (Python implementation of client-side stretching)
2. `POST /v1/account/create` → uid, sessionToken, keyFetchToken
3. `POST /v1/account/login` → sessionToken, keyFetchToken
4. `GET /v1/account/keys` → decrypt bundle → verify kA, derive kB
5. `POST /v1/account/scoped-key-data` → verify key metadata
6. `POST /v1/oauth/authorization` → code
7. `POST /v1/oauth/token` → JWT access_token
8. `GET /1.0/sync/1.5` with Bearer JWT → HAWK credentials
9. Print success

```bash
git add tools/fxa_integration_test.py
git commit -m "test: add end-to-end FxA auth flow integration test"
```

---

### Task 29: Run Full Test Suite and Final Cleanup

**Step 1: Run all Python tests**

Run: `cd lambda && uv run pytest tests/ -x -q`
Expected: All pass with 100% coverage on new code.

**Step 2: Run all linters**

Run: `cd lambda && uv run black --check src/ tests/ && uv run isort --check-only src/ tests/ && uv run mypy src/`

**Step 3: TypeScript compile check**

Run: `npx tsc --noEmit`

**Step 4: Frontend build**

Run: `cd frontend && npm run build`

**Step 5: Smithy build**

Run: `cd smithy && ./gradlew clean build`

**Step 6: Final commit if any cleanup needed**

```bash
git commit -m "chore: final cleanup and lint fixes"
```

---

## Task Dependency Graph

```
Phase 1 (Foundation):   Task 1 → Task 2 → Task 3 → Task 4 → Task 5
                                                          ↓
Phase 2 (Account):      Task 6 → Task 7 → Task 8 → Task 9 → Task 10 → Task 11
                                                                         ↓
Phase 3 (Session):      Task 12
                          ↓
Phase 4 (OAuth):        Task 13 → Task 14 → Task 15
                                              ↓
Phase 5 (Discovery):    Task 16
                          ↓
Phase 6 (Integration):  Task 17 → Task 18
                                    ↓
Phase 7 (CDK):          Task 19 → Task 20 → Task 21 → Task 22
                                                         ↓
Phase 8 (Frontend):     Task 23 → Task 24 → Task 25 → Task 26 → Task 27
                                                                    ↓
Phase 9 (Final):        Task 28 → Task 29
```

**Parallelizable:** Phase 7 (CDK) and Phase 8 (Frontend) can run in parallel once Phase 6 is complete. Tasks 1-5 (services) have no CDK/frontend dependencies and can be developed independently.
