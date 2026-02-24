# FxA Auth Shim: Native Firefox Sync via OIDC Provider

## Problem

Firefox's built-in Sync is tightly coupled to Firefox Accounts (FxA). The native sign-in flow requires an FxA-compatible auth server that implements a specific key derivation protocol (onepw), session token management, and OAuth token issuance. Without this, users must manually configure `about:config` with a token server URI obtained from an external setup page.

The existing ffsync deployment uses a generic OIDC provider for authentication, which Firefox doesn't understand. Users cannot use "Sign in to Sync" in Firefox.

## Solution

Implement a minimal FxA-compatible auth server as a serverless Lambda, consolidated with the existing token server under a single `auth.{stage}.{BASE_DOMAIN}` domain. Extend the existing frontend SPA to serve as the FxA content server, communicating with Firefox via the WebChannel API.

Users set one `about:config` preference and then use Firefox's native "Sign in to Sync" flow. Authentication is two-step: passkey via the OIDC provider (identity verification), then a sync password (for client-side encryption key derivation).

## Architecture

```
Firefox Browser
    |
    +--> Content Server (existing CloudFront SPA at {stage}.{BASE_DOMAIN})
    |    |-- /.well-known/fxa-client-configuration  (static JSON in S3)
    |    |-- /signin  (FxA WebChannel sign-in flow)
    |    +-- /signup  (FxA WebChannel account creation flow)
    |
    +--> Auth Server (Lambda at auth.{stage}.{BASE_DOMAIN})
    |    |-- /v1/account/*    (FxA account management + key fetch)
    |    |-- /v1/session/*    (session management)
    |    |-- /v1/oauth/*      (OAuth token issuance)
    |    |-- /1.0/sync/1.5    (existing sync token endpoint)
    |    +-- /.well-known/openid-configuration, /v1/jwks  (OIDC discovery)
    |
    +--> Storage Server (existing Lambda at storage.{stage}.{BASE_DOMAIN})
         +-- validates HAWK credentials (unchanged)
```

### End-to-end sign-in flow

1. User sets `identity.fxaccounts.autoconfig.uri = https://{stage}.{BASE_DOMAIN}` in `about:config`
2. Firefox fetches `/.well-known/fxa-client-configuration` from CloudFront, discovers all service URLs
3. User clicks "Sign in to Sync" in Firefox
4. Firefox opens `/signin?context=oauth_webchannel_v1&service=sync` in a tab
5. SPA authenticates user with OIDC provider (passkey)
6. SPA prompts for sync password
7. SPA stretches password client-side (PBKDF2 + HKDF) into `authPW` + `unwrapBKey`
8. SPA calls auth server `POST /v1/account/login` with `authPW`
9. Auth server validates, returns `sessionToken` + `keyFetchToken`
10. SPA calls `POST /v1/oauth/authorization` to get OAuth code
11. SPA sends `fxaccounts:oauth_login` WebChannel message to Firefox with code + key info
12. Firefox calls `GET /v1/account/keys` with keyFetchToken, gets `kA` + `wrapKB`
13. Firefox derives `kB = wrapKB XOR unwrapBKey`, derives sync encryption keys
14. Firefox calls `POST /v1/oauth/token` to exchange code for access_token JWT
15. Firefox sends JWT to `GET /1.0/sync/1.5`, gets HAWK credentials
16. Firefox syncs with Storage Server using HAWK

## Auth Server API Surface

### Called by Firefox (after WebChannel sign-in)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/v1/account/keys` | keyFetchToken | Return encrypted kA + wrapKB bundle (single-use) |
| `GET` | `/v1/account/profile` | sessionToken or OAuth | Return email, uid for Firefox UI |
| `POST` | `/v1/account/scoped-key-data` | sessionToken | Return key rotation metadata for sync scope |
| `GET` | `/v1/session/status` | sessionToken | Check session validity (Firefox polls) |
| `POST` | `/v1/session/destroy` | sessionToken | Sign out |
| `POST` | `/v1/oauth/token` | code or refreshToken | Exchange code for JWT, or refresh |
| `POST` | `/v1/oauth/destroy` | client_id | Revoke token |

### Called by the Content Server SPA (during sign-in)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/v1/account/create` | OIDC Bearer | Create account with email + authPW |
| `POST` | `/v1/account/login` | none | Verify authPW, return sessionToken + keyFetchToken |
| `GET` | `/v1/account/status` | none | Check if email has an account |
| `POST` | `/v1/oauth/authorization` | sessionToken | Issue OAuth authorization code |

### Discovery

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/.well-known/openid-configuration` | OIDC discovery for JWT validation |
| `GET` | `/v1/jwks` | Public signing keys |

### Existing (unchanged)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/1.0/sync/1.5` | Exchange OAuth JWT for HAWK credentials |

### Auth mechanisms

- **sessionToken**: Client derives `tokenId` + `reqHMACkey` from raw token via HKDF. Request includes Hawk-style Authorization header with HMAC signature. Lambda verifies HMAC.
- **keyFetchToken**: Same derivation as sessionToken, but single-use (deleted after key fetch).
- **OAuth Bearer**: Standard `Authorization: Bearer <jwt>` for the sync token endpoint and profile access.
- **OIDC Bearer**: OIDC access token from the identity provider, validated during account creation to link the FxA account to the OIDC identity.

### Explicitly out of scope

- Account deletion, password change/reset (add later)
- Device registration, push notifications, send-tab
- Advanced session management (duplicate, reauth)
- BrowserID/certificate signing (deprecated)

## Key Derivation Protocol

### Client-side password stretching (SPA, Web Crypto API)

```
salt = "identity.mozilla.com/picl/v1/quickStretch:" + email_utf8
quickStretchedPW = PBKDF2-SHA256(password_utf8, salt, iterations=1000, length=32)

authPW     = HKDF-SHA256(quickStretchedPW, salt="", info="identity.mozilla.com/picl/v1/authPW",     length=32)
unwrapBKey = HKDF-SHA256(quickStretchedPW, salt="", info="identity.mozilla.com/picl/v1/unwrapBkey", length=32)
```

SPA sends `authPW` to auth server. `unwrapBKey` stays in browser, passed to Firefox via WebChannel.

### Server-side account creation

```
# Derive verification hash
verifyHash = HKDF-SHA256(authPW, salt="", info="identity.mozilla.com/picl/v1/verifyHash", length=32)

# Generate encryption keys
kA     = random(32 bytes)    # class A key
wrapKB = random(32 bytes)    # wrapped class B key

# Store: email, uid, verifyHash, kA, wrapKB
```

`kB = wrapKB XOR unwrapBKey` is the actual sync encryption key. Neither server nor client chooses it. The server never sees `kB`.

### Login verification

```
verifyHash = HKDF-SHA256(authPW, info="identity.mozilla.com/picl/v1/verifyHash")
# constant-time compare against stored verifyHash

# On success, generate tokens:
sessionToken  = random(32 bytes)
keyFetchToken = random(32 bytes)

# Derive tokenIds for storage (client derives same values):
sessionTokenId  = HKDF(sessionToken,  info="identity.mozilla.com/picl/v1/sessionToken")[0:32]
keyFetchTokenId = HKDF(keyFetchToken, info="identity.mozilla.com/picl/v1/keyFetchToken")[0:32]
```

### Key fetch (single-use)

Firefox derives from raw `keyFetchToken`:
```
derived       = HKDF(keyFetchToken, info="identity.mozilla.com/picl/v1/keyFetchToken", length=3*32)
tokenId       = derived[0:32]       # Hawk Authorization header
reqHMACkey    = derived[32:64]      # request HMAC signing
keyRequestKey = derived[64:96]      # response decryption
```

Server encrypts the key bundle:
```
keys    = HKDF(keyRequestKey, info="identity.mozilla.com/picl/v1/account/keys", length=3*32)
hmacKey = keys[0:32]
xorKey  = keys[32:96]

ciphertext = (kA || wrapKB) XOR xorKey
mac        = HMAC-SHA256(hmacKey, ciphertext)
bundle     = ciphertext || mac
```

Firefox decrypts to get `kA` and `wrapKB`, computes `kB = wrapKB XOR unwrapBKey`.

### Sync key derivation (Firefox internal)

Firefox derives sync encryption keys from `kB` using scoped-key-data metadata:
```
syncKey       = HKDF(kB, salt=uid, info="identity.mozilla.com/picl/v1/oldsync", length=64)
encryptionKey = syncKey[0:32]
hmacKey       = syncKey[32:64]
```

## Data Model

### New table: `ffsync-auth-{stage}`

Single DynamoDB table with PK-only access patterns and TTL on `expiry`.

**Account records:**
```
PK: ACCOUNT#<uid>
  email: string
  uid: string (UUID)
  verifyHash: string (64 hex chars)
  kA: string (64 hex chars)
  wrapKB: string (64 hex chars)
  oidcSub: string (OIDC subject claim from identity provider)
  verified: boolean
  createdAt: number (epoch ms)
```

**Email lookup:**
```
PK: EMAIL#<normalized_email>
  uid: string
```

**Session tokens:**
```
PK: SESSION#<tokenId_hex>
  uid: string
  createdAt: number (epoch ms)
  verified: boolean
  expiry: number (TTL, 30 days)
```

**Key fetch tokens (single-use):**
```
PK: KEYFETCH#<tokenId_hex>
  uid: string
  keyFetchToken: string (64 hex chars, raw token for deriving keyRequestKey)
  expiry: number (TTL, 5 minutes)
```

**OAuth authorization codes:**
```
PK: OAUTHCODE#<code>
  uid: string
  clientId: string
  scope: string
  codeChallengeMethod: string
  codeChallenge: string
  createdAt: number (epoch ms)
  expiry: number (TTL, 10 minutes)
```

**OAuth refresh tokens:**
```
PK: REFRESH#<token_hash>
  uid: string
  clientId: string
  scope: string
  createdAt: number (epoch ms)
  expiry: number (TTL, 30 days)
```

### Existing tables (unchanged)

- `ffsync-token-users-{stage}` — sync user records (generation, client state). Looked up by `oidcSub` from the OAuth JWT `sub` claim.
- `ffsync-token-cache-{stage}` — HAWK credential cache.

### Signing key

```
KMS Key: ffsync-auth-signing-{stage}
  KeySpec: RSA_2048
  KeyUsage: SIGN_VERIFY
```

Lambda calls `kms:Sign` to sign OAuth JWTs, `kms:GetPublicKey` to serve the JWKS endpoint. Private key never leaves KMS.

## Frontend Changes

### Routing

Add React Router to the existing SPA:

| Path | Purpose |
|------|---------|
| `/` | Existing manual-setup flow (kept during transition) |
| `/signin` | FxA sign-in (Firefox navigates here with WebChannel context) |
| `/signup` | FxA account creation |

The SPA detects `context=oauth_webchannel_v1` in URL params to distinguish FxA mode from manual mode.

### FxA sign-in flow

1. OIDC authentication: reuse existing Pocket ID flow (passkey)
2. Sync password prompt: new form component
3. Client-side key stretching: PBKDF2 + HKDF via Web Crypto API
4. Auth server calls: create/login account
5. WebChannel message: send OAuth code + key info to Firefox

### New modules

| File | Purpose |
|------|---------|
| `lib/fxa-crypto.ts` | PBKDF2 + HKDF key stretching via Web Crypto API |
| `lib/webchannel.ts` | WebChannel send/receive with Firefox |
| `lib/auth-client.ts` | HTTP client for auth server API |
| `components/SignInPage.tsx` | FxA sign-in flow |
| `components/SignUpPage.tsx` | FxA account creation flow |
| `components/SyncPasswordForm.tsx` | Email + sync password form |

### Config changes

`config.json` gains `authServerUrl`, loses `tokenServerUrl`:
```json
{
  "oidcProviderUrl": "...",
  "clientId": "...",
  "redirectUri": "https://{stage}.{BASE_DOMAIN}",
  "authServerUrl": "https://auth.{stage}.{BASE_DOMAIN}",
  "scopes": ["openid", "profile", "email"]
}
```

### Static files

`fxa-client-configuration` deployed to S3 alongside `config.json`:
```json
{
  "auth_server_base_url": "https://auth.{stage}.{BASE_DOMAIN}",
  "oauth_server_base_url": "https://auth.{stage}.{BASE_DOMAIN}",
  "profile_server_base_url": "https://auth.{stage}.{BASE_DOMAIN}",
  "sync_tokenserver_base_url": "https://auth.{stage}.{BASE_DOMAIN}"
}
```

## CDK Infrastructure

### Service rename

`Service.TOKEN` becomes `Service.AUTH`. Domain: `auth.{stage}.{BASE_DOMAIN}`.

Renames throughout ServiceStack: `tokenApiDomain` to `authApiDomain`, `tokenHandler` to `authHandler`, `tokenApi` to `authApi`. Lambda function name: `ffsync-auth-api-{stage}`.

### New resources in ServiceStack

- DynamoDB table `ffsync-auth-{stage}` with TTL on `expiry`
- KMS key `ffsync-auth-signing-{stage}` (RSA_2048, SIGN_VERIFY)
- Lambda grants: `authTable.grantReadWriteData`, `signingKey.grantSign`, `signingKey.grant("kms:GetPublicKey")`

### Lambda environment variables

Existing variables unchanged. New additions:
- `AUTH_TABLE_NAME` — auth DynamoDB table
- `AUTH_SIGNING_KEY_ID` — KMS key ARN

### Smithy model

`TokenService` becomes `AuthService` using resource-based modeling:

```smithy
service AuthService {
    version: "1.0"
    resources: [Account, Session, OAuth]
    operations: [GetToken, OIDCDiscovery, JWKS]
}

resource Account {
    identifiers: { uid: String }
    create: AccountCreate
    read: AccountProfile
    operations: [AccountLogin, AccountStatus, AccountKeys, ScopedKeyData]
}

resource Session {
    identifiers: { tokenId: String }
    read: SessionStatus
    operations: [SessionDestroy]
}

resource OAuth {
    operations: [OAuthAuthorization, OAuthToken, OAuthDestroy]
}
```

Model files split across `smithy/models/auth/account.smithy`, `auth/session.smithy`, `auth/oauth.smithy`.

### JWT validation

- OIDC provider tokens: existing `OIDCValidator` validates during account creation
- Self-issued OAuth JWTs: new `JWTVerifier` validates via `kms:Verify` or cached KMS public key. Used by `/1.0/sync/1.5` handler.

No circular self-discovery.

### FrontendStack

Props: `tokenApiDomain` becomes `authApiDomain`. BucketDeployment adds `fxa-client-configuration` as a second `Source.jsonData()` entry.

## Firefox Configuration

Single `about:config` setting:

```
identity.fxaccounts.autoconfig.uri = https://{stage}.{BASE_DOMAIN}
```

Firefox discovers all service URLs from `/.well-known/fxa-client-configuration`. No other preferences required.

## Testing Strategy

### Unit tests (Python, pytest)

Test crypto against FxA published test vectors:
- HKDF derivation of authPW, verifyHash, unwrapBKey
- Key bundle encrypt/decrypt round-trip
- Token ID derivation from raw tokens
- Hawk request HMAC verification
- JWT sign/verify with KMS

Each API endpoint gets route tests following existing patterns in `tests/routes/`.

### Frontend tests (TypeScript)

- PBKDF2 + HKDF output matches FxA test vectors
- WebChannel message format matches Firefox expectations
- FxA context detection from URL parameters

### Integration test

Script exercising the full chain without a browser:
1. Stretch password, create account, login
2. Fetch keys, decrypt bundle, verify kB derivation
3. Get OAuth code, exchange for JWT
4. Exchange JWT for HAWK credentials at token endpoint
5. Verify HAWK works against storage server

### Smoke test

Set `identity.fxaccounts.autoconfig.uri` in Firefox, sign in, verify bookmarks sync between two instances.
