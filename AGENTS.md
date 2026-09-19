# Agent Context for ffsync

This file provides context for AI coding agents working on this repository. It contains build commands, conventions, and gotchas to help agents work effectively.

> RFC 2119: MUST = required, SHOULD = recommended, MAY = optional

## Critical Rules

**MUST update this file when:** corrected about how something works, or user says "remember this"

**MUST update README.md when:** functionality or setup steps change

**MUST run `lambda/scripts/codegen.sh` before any Python work.** `lambda/src/shared/generated/` is git-ignored and `src/shared/models.py` imports from it, so on a fresh clone every import, test, mypy and flake8 run fails until you generate it. See [Codegen](#codegen-smithy--pydantic).

**MUST run Python tools as `uv run <tool>` from `lambda/`.** This code is Python 3.14 and uses PEP 758 syntax that the system `python3` (3.12) cannot parse. See [PEP 758](#pep-758-except-clauses-are-not-syntax-errors).

## Package Overview

| Field | Value |
|-------|-------|
| Package | @layertwo/ffsync |
| Build System | npm (CDK), pytest (Lambda), Gradle (Smithy), Vite (Frontend) |
| Languages | TypeScript (CDK + Frontend), Python 3.14 (Lambda) |
| Runtime | AWS Lambda (ARM64) |
| Purpose | Self-hosted Firefox Sync protocol implementation on AWS |
| Account / Region | `830583812777` / `us-west-2` (hardcoded in `lib/config.ts`) |
| Stages | `prod` only |

## Quick Commands

| Task | Command | Location |
|------|---------|----------|
| **Generate models (do this first)** | `./scripts/codegen.sh` | `lambda/` |
| Test Lambda | `uv run pytest` | `lambda/` |
| Test Lambda (serial, for pdb) | `uv run pytest -n 0` | `lambda/` |
| Test specific pattern | `uv run pytest -k <pattern>` | `lambda/` |
| Format Lambda | `uv run black src/ tests/ && uv run isort src/ tests/` | `lambda/` |
| Lint Lambda | `uv run flake8 src/ tests/` | `lambda/` |
| Type check Lambda | `uv run mypy` | `lambda/` |
| Build Smithy | `./gradlew smithyBuild` | `smithy/` |
| Build CDK | `npm run build` | root |
| CDK Synth | `npm run cdk synth` | root (needs Docker + smithy build) |
| Format CDK | `npm run format` | root |
| Frontend dev | `npm run dev` | `frontend/` |
| Frontend test | `npm test` | `frontend/` |
| Frontend build | `npm run build` | `frontend/` |
| Tools CLI | `uv sync && uv run python ffsync_client.py ...` | `tools/` |

Parallel execution (`-n auto`) and the 100% coverage gate are already in `addopts`; do not pass them.

**The coverage gate applies to subset runs too**, so `-k` / single-file runs exit **1** with `FAIL Required test coverage of 100% not reached` even when every selected test passes (verified: `uv run pytest tests/shared/test_token.py` → `7 passed`, coverage 30%, exit 1). Read the `passed`/`failed` counts rather than the exit code, or pass `--no-cov` while iterating.

## Architecture

```
Firefox Client
    │
    ├─ authPW / session Hawk → Auth API → DynamoDB (auth) + KMS (RSA sign)
    │                             ├─ FxA-compatible auth (account, session, OAuth, devices)
    │                             └─ Issues self-signed JWTs for token/profile servers
    │
    ├─ JWT Bearer → Token API → DynamoDB (token-users, token-cache) + KMS (GetPublicKey)
    │                  └─ Exchanges JWT for HAWK credentials (300s TTL)
    │
    ├─ JWT Bearer → Profile API → DynamoDB (auth) + KMS (GetPublicKey)
    │                  └─ Returns user profile (email, uid, locale)
    │
    ├─ HAWK auth → Storage API → DynamoDB (storage BSOs + token-cache)
    │                  └─ HawkAuthMiddleware validates inline (no separate authorizer)
    │
    └─ WebSocket → Channel API → DynamoDB (channel)
                       └─ QR-code device pairing relay ($connect/$disconnect/$default)

Browser SPA ─ OIDC login → Auth API (/v1/oidc/config, /v1/oidc/exchange server-side proxy)

CloudFront → S3 (frontend SPA)
          └─ inline viewer-request Function synthesizes /.well-known/fxa-client-configuration
             (advertises pairing_server_base_uri: wss://channel.<stage>.<domain>)
```

Firefox itself never performs OIDC login — it uses `authPW` (`src/routes/auth/account_login.py`). OIDC is the SPA calling the Auth API's server-side proxy routes.

**Five Lambda Functions.** All ship the *same bundle*: CDK sets `index: src/entrypoint/__init__.py` and selects behaviour via `handler: <service>_api_handler`. A new entrypoint MUST also be re-exported from `lambda/src/entrypoint/__init__.py` under that exact alias.

| Function | Entrypoint → handler | Purpose | Size / timeout |
|---|---|---|---|
| Auth API | `auth_api.py` → `auth_api_handler` | FxA-compatible auth: account, login, OAuth, OIDC, sessions, devices | 512 MB / 29 s |
| Token API | `token_api.py` → `token_api_handler` | Exchanges self-signed JWTs for HAWK credentials | 512 MB / 29 s |
| Profile API | `profile_api.py` → `profile_api_handler` | User profile via self-signed JWT Bearer | 512 MB / 29 s |
| Storage API | `storage_api.py` → `storage_api_handler` | SyncStorage v1.5 REST API (BSOs) | 512 MB / 29 s |
| Channel API | `channel_api.py` → `channel_api_handler` | WebSocket device-pairing relay | 256 MB / 10 s |

29 s is the API Gateway REST integration hard cap — raising `timeout` alone cannot fix request timeouts.

Use `@lambda_entrypoint` (`src/environment/service_provider.py`) on new handlers: it injects the `lru_cache`d singleton `ServiceProvider` when none is passed, and flushes CloudWatch EMF metrics in a `finally` block.

**Five API Gateways — four REST + one WebSocket:**

- **Auth API** (SpecRestApi, edge): `auth.<stage>.<BASE_DOMAIN>` — mixed auth: `authPW` (account create/login/keys), IdP OIDC Bearer (account create only), session Hawk (session, scoped-key-data, OAuth authorization, device routes), unauthenticated (JWKS, OIDC discovery, `/v1/oauth/token`, `/v1/oauth/destroy`)
- **Token API** (SpecRestApi, edge): `token.<stage>.<BASE_DOMAIN>` — Bearer self-signed JWT
- **Profile API** (SpecRestApi, edge): `profile.<stage>.<BASE_DOMAIN>` — Bearer self-signed JWT
- **Storage API** (SpecRestApi, edge): `storage.<stage>.<BASE_DOMAIN>` — HAWK (inline middleware)
- **Channel API** (API Gateway v2 `WebSocketApi`, regional): `wss://channel.<stage>.<BASE_DOMAIN>` — no auth on `$connect`; bounded to 3 connections and 10 messages per channel with a 300 s TTL (`src/services/channel_service.py`)

All four REST APIs set `disableExecuteApiEndpoint: true`, so `https://<id>.execute-api.<region>.amazonaws.com/...` always returns 403 — **manual testing MUST use the custom domain.** The Channel API has no Smithy model or OpenAPI spec; it is declared directly in `lib/stacks/service.ts`.

**Five DynamoDB Tables** (single-table designs, string `PK`; TTL attribute is `expiry`, not `ttl`):

| Table | Contents |
|---|---|
| `ffsync-storage-<stage>` | BSOs + collection metadata. `PK` + `SK` (the only table with a sort key). GSI `UserCollectionsIndex` (`user_id` / `name`, `ProjectionType.ALL`). **No TTL configured** even though BSO items write an absolute `expiry`. |
| `ffsync-token-users-<stage>` | `USER#<uid>` — client state and generation |
| `ffsync-token-cache-<stage>` | HAWK credential cache + Hawk nonces (TTL) |
| `ffsync-auth-<stage>` | `ACCOUNT#`, `EMAIL#`, `OIDCSUB#`, `SESSION#`, `KEYFETCH#`, `OAUTHCODE#`, `REFRESH#`, `DEVICE#` (TTL) |
| `ffsync-channel-<stage>` | `CHANNEL#<channelId>`, `CONN#<connectionId>` (TTL, 300 s) |

Long-lived auth-table items (`ACCOUNT#`, `EMAIL#`, `OIDCSUB#`, `DEVICE#`) MUST NOT carry an `expiry` field; any new ephemeral item type MUST set one.

**Environment Configuration.** Most variables are read lazily in a `ServiceProvider` cached property via `os.environ[...]`, so a missing one raises `KeyError` on first access *during a request* — not at import or cold start. Three use `.get()` and fail **silently** instead: `BASE_DOMAIN` (→ `storage_domain` becomes the string `"storage.None"`), `AWS_REGION`, and `OIDC_CACHE_TTL_SECONDS` (defaults to `3600`). Variables are scoped per Lambda, but `tests/conftest.py` sets all of them for every test, so tests cannot catch missing CDK wiring. Full list: `grep -rn os.environ src/`.

| Variable | Set on | Notes |
|---|---|---|
| `BASE_DOMAIN` | Auth, Token, Profile, Storage (**not** Channel) | Derives storage host, JWT issuer (`https://auth.<BASE_DOMAIN>`), CORS origin |
| `STORAGE_TABLE_NAME` | Storage | |
| `TOKEN_USERS_TABLE_NAME` | Token | |
| `TOKEN_CACHE_TABLE_NAME` | Token, Storage | Storage reads it for HAWK validation |
| `AUTH_TABLE_NAME` | Auth, Profile | |
| `CHANNEL_TABLE_NAME` | Channel | |
| `AUTH_SIGNING_KEY_ID` | Auth, Token, Profile | KMS RSA-2048 key |
| `OIDC_PROVIDER_URL`, `OIDC_CLIENT_ID` | Auth only | From SSM `/ffsync/<stage>/oidc-provider-url`, `/ffsync/<stage>/client-id` |
| `CLOCK_SKEW_TOLERANCE` | Auth | OIDC JWT skew (300 s) |
| `OIDC_CACHE_TTL_SECONDS` | Auth | Provider config + JWKS cache (3600 s) |
| `HAWK_TIMESTAMP_SKEW_TOLERANCE` | Auth, Token, Storage | 60 s — Auth needs it for `session_hawk_middleware` |
| `TOKEN_DURATION` | Token, Storage | HAWK credential duration (300 s) |
| `RETRY_AFTER_SECONDS` | Token | `Retry-After` on 503 (30 s) |

## Project Structure

```
lib/                          # CDK infrastructure (TypeScript)
├── app.ts                    # Synthesizes GitHubOidcStack, Service-prod, Frontend-prod, Monitoring-prod
├── config.ts                 # Account/region/stage config (prod only)
├── config/service.ts         # Service enum (AUTH, TOKEN, PROFILE, STORAGE, CHANNEL)
├── utils.ts
└── stacks/
    ├── service.ts            # 5 Lambdas, 4 REST + 1 WebSocket API, 5 tables, KMS, ACM, Route53
    ├── frontend.ts           # CloudFront + S3, inline fxa-client-configuration Function
    ├── github-oidc.ts        # GitHub Actions OIDC deploy role
    └── monitoring.ts         # CloudWatch dashboard only (no alarms, no SNS)

test/                         # The only CDK test (frontend.test.ts), run by root jest.config.ts
                              # NOT run by any workflow; its afterAll deletes frontend/dist/

frontend/                     # React SPA (Vite + Tailwind v4)
├── src/
│   ├── lib/pairing-channel/  # WebSocket pairing client (+ __tests__, 111 vitest tests)
│   ├── lib/sanitize.ts       # dompurify wrapper
│   └── index.css             # Tailwind v4 CSS-first config (@theme / .dark blocks)
├── vite.config.ts            # @tailwindcss/vite plugin, happy-dom test env
└── package.json              # React 19, react-router v8, radix-slot, qrcode.react

lambda/                       # Python Lambda functions
├── scripts/codegen.sh        # Smithy OpenAPI → pydantic models (REQUIRED before any work)
├── src/
│   ├── entrypoint/           # auth_api, token_api, profile_api, storage_api, channel_api
│   ├── middlewares/
│   │   ├── hawk_auth.py      # Unified Hawk auth (storage router-level + session per-route)
│   │   ├── request_logging.py
│   │   └── weave_timestamp.py
│   ├── routes/
│   │   ├── auth/             # FxA auth: account, login, keys, OAuth, OIDC, sessions, devices
│   │   ├── bso/              # BSO CRUD
│   │   ├── collections/      # Collection management
│   │   ├── info/             # collections, counts, usage, quota, configuration
│   │   ├── profile/          # Profile (JWT Bearer)
│   │   ├── storage/          # delete_all + delete_root
│   │   └── token/            # Token request
│   ├── services/
│   │   ├── api_router.py     # Route dispatch + exception handlers
│   │   ├── storage_manager.py    user_manager.py       hawk_service.py
│   │   ├── oidc_validator.py     jwt_service.py        jwt_verifier.py
│   │   ├── auth_account_manager.py                     fxa_crypto.py
│   │   ├── fxa_token_manager.py  oauth_code_manager.py token_generator.py
│   │   ├── channel_service.py    # WebSocket device-pairing relay
│   │   └── device_manager.py     # FxA device records
│   ├── shared/               # exceptions, base_route, oidc, token, user, utils
│   │   ├── models.py         # Single import point: re-exports generated models
│   │   ├── generated/        # GENERATED, GIT-IGNORED — run scripts/codegen.sh
│   │   └── _codegen_base.py  # Hand-written base class injected into generated models
│   └── environment/          # service_provider.py (DI + @lambda_entrypoint)
├── tests/                    # Loosely mirrors src/ (see Test structure below)
│   ├── fixtures/             # boto.py (star-imported by conftest.py) + integration.py (import by name)
│   └── integration/          # token→storage, Mozilla token-server spec
└── pyproject.toml            # Deps + pytest/black/isort/flake8/mypy config

smithy/                       # API contract definitions (Gradle)
├── models/main.smithy        # Four service shapes + CDK placeholder traits
├── models/                   # Per-service operation/shape models
├── build.gradle.kts          # outputDirectory → repo-root build/smithy
└── smithy-build.json         # Four projections: storage, auth, token, profile

tools/                        # CLI tools (uv-managed, requires-python >=3.14)
├── ffsync_client.py          # Click CLI, signs with requests-hawk
├── get_hawk_token.py         # OIDC → HAWK credential exchange
├── pyproject.toml / uv.lock
└── README.md
```

## Codegen (Smithy → pydantic)

`lambda/src/shared/generated/` holds the pydantic wire models. It is **git-ignored** and `rm -rf`'d at the start of every codegen run, so hand edits are silently destroyed. To change a model, change `smithy/models/` and regenerate.

```bash
# Option A — standalone CLI (brew install smithy-cli)
cd lambda && ./scripts/codegen.sh

# Option B — Gradle (what CI does). Note Gradle writes to the REPO ROOT build/smithy
(cd smithy && ./gradlew smithyBuild)
cd lambda && SMITHY_BUILD_DIR="$(git rev-parse --show-toplevel)/build/smithy" ./scripts/codegen.sh
```

- `./gradlew smithyBuild` alone updates the OpenAPI specs CDK reads but leaves the Python models **stale** — any IDL change needs both steps.
- Generated code IS linted and type-checked (`black`, `isort`, `flake8`, `mypy` all cover `src/`), but is omitted from coverage (`*/generated/*`). The only flake8 carve-out is `src/shared/generated/*:F722`.
- `src/shared/_codegen_base.py` is hand-written and passed as `--base-class`; it gives every generated model `populate_by_name=True`. Do not delete it.
- `src/shared/models.py` is the **only** module that may import `src.shared.generated.*`. Everything else imports from `models.py`.
- smithy-openapi drops `@default` traits, so IDL defaults do not survive codegen. They are restored by subclassing in `models.py` (e.g. `OAuthTokenOutput.token_type = "bearer"`, `ProfileOutput.locale = "en-US"`).
- Adding or renaming a service means touching **four** places with the same lowercase key: a projection in `smithy/smithy-build.json`, the service shape in `smithy/models/main.smithy`, the `for svc in storage auth token profile` loop in `lambda/scripts/codegen.sh`, and the `Service` enum in `lib/config/service.ts`.

## Key Conventions

### Python (Lambda)

- **Line length**: 100 (Black)
- **Type hints**: mypy runs strict over **both** `src/` and `tests/` — `disallow_untyped_defs`, `check_untyped_defs`, `warn_unused_ignores`. Every test function needs `-> None`; every fixture needs annotated params. An unnecessary `# type: ignore` is itself an error.
- **`ignore_missing_imports` is scoped to `mohawk` only**, deliberately. Globally it turns an uninstalled stub package into a silent `Any`, which makes annotations look like type safety while checking nothing. Add a per-module override for a new stubless dependency; do not re-enable it globally.
- **Models**: pydantic v2, generated from Smithy (see [Codegen](#codegen-smithy--pydantic)). Serialize with `model_dump_json()`. Plain `@dataclass` is only for internal value objects that never cross the wire (`shared/token.py`, `shared/oidc.py`, `HawkCredentials`).
- **camelCase wire shapes**: generated models use snake_case fields with pydantic aliases (`pushCallback`, `lastAccessTime`, `sessionTokenId`). Serialize those with `model_dump_json(by_alias=True)`. Input accepts both spellings (`populate_by_name=True`, `extra="allow"`).
- **Never pass floats to DynamoDB**: boto3 raises `TypeError: Float types are not supported`. Use `to_dynamo_dict()`, `bso_to_item()`, `collection_to_item()` (`shared/models.py`) or `UserRecord.to_item()`, which convert floats to `Decimal(str(v))`.
- **Authenticated routes read identity from the event, not headers**: `HawkAuthMiddleware` injects `event["requestContext"]["hawk_uid"]` and (session Hawk) `hawk_token_id`. Use `BaseRoute.hawk_uid(event)` and `BaseRoute.unauthorized()`; do not re-parse `Authorization`.
- **New exceptions**: subclass `SyncStorageException` with class attributes only — `status_code`, `error_code`, optional `mozilla_code`, `default_message`. Never override `__init__`; the base already resolves the default message and accepts `retry_after` / `backoff` / `alert` (rendered as `Retry-After`, `X-Weave-Backoff`, `X-Weave-Alert`).
- **A new route needs registering in two places**: the operation in `smithy/models/<service>/` (each REST API is a `SpecRestApi` built from the generated OpenAPI spec, so a path absent from the spec returns 403 regardless of the Python code) *and* the route class in `service_provider.py`'s router list.
- **Logging**: `from aws_lambda_powertools import Logger`
- **Route structure**: `routes/{resource}/{action}.py`
- **Service layer**: business logic in `services/`

### TypeScript (CDK)

- **Target**: ES2020, Module: node20, strict mode, `noImplicitReturns`
- **Imports**: auto-sorted by the Prettier plugin
- **Credentials**: `cdk.json` sets **no** profile — synth/deploy use ambient AWS credentials (CI assumes `CDK_DEPLOY_ROLE_ARN` via GitHub OIDC)
- **No CI gate**: nothing lints or unit-tests the TypeScript. `npm run check-format` and the root `npm test` exist but no workflow runs them; the only gate is `npm run build` + `cdk synth`.
- **The root `npm test` deletes `frontend/dist/`.** There is exactly one CDK test (`test/frontend.test.ts`); it stubs a `frontend/dist/index.html` in `beforeAll` because `Source.asset` needs a non-empty directory, then `rmSync`s the whole directory in `afterAll`. Running it after a real `npm run build` in `frontend/` destroys those assets, and the next `cdk synth`/`deploy` picks up whatever is left. Rebuild the frontend afterwards.

### Frontend (React)

- **Framework**: React 19 + Vite + Tailwind CSS v4, react-router v8
- **Tailwind v4 is CSS-first**: the `@tailwindcss/vite` plugin plus `@theme` / `.dark` blocks in `src/index.css`. There is no `tailwind.config.js` or `postcss.config.js` — **do not add either.**
- **Do not lint the frontend.** `frontend/` has no `eslint.config.*`, so `npm run lint` resolves to the repo-root config (CDK/Prettier rules) and reports ~13,500 spurious errors. The enforced gates are `npm test` and `tsc -b && vite build`.
- **Tests**: `npm test` = `vitest run` — 111 tests under `src/lib/pairing-channel/__tests__/` (happy-dom). These gate deployment.

### API Design

- **Timestamps**: epoch seconds, 2 decimal places (e.g. `1702345678.12`)
- **Auth**: JWT Bearer → HAWK credentials (300 s)
- **Headers**: `X-Last-Modified`, `X-If-Unmodified-Since` for optimistic concurrency
- **Error codes**: 400 (validation), 401 (auth), 403 (uid mismatch), 409 (conflict), 412 (precondition), 413 (too large), 507 (quota)

## Key Dependencies

| Dependency | Purpose | Layer |
|------------|---------|-------|
| aws-cdk-lib | Infrastructure as Code | CDK |
| cdk-monitoring-constructs | Dashboard | CDK |
| uv-python-lambda | Lambda bundling (Docker) | CDK |
| AWS Lambda Powertools | Logging, APIGatewayRestResolver, metrics | Lambda |
| pydantic (v2) | Wire model validation/serialization | Lambda |
| datamodel-code-generator | Smithy OpenAPI → pydantic models | Lambda (dev) |
| types-boto3[apigatewaymanagementapi,dynamodb,kms] | DynamoDB/KMS/APIGW type stubs | Lambda (dev) |
| PyJWT | JWT handling | Lambda |
| mohawk | HAWK authentication (no type stubs) | Lambda |
| cryptography | Crypto operations | Lambda |
| requests | HTTP client (OIDC discovery) | Lambda |
| boto3 | AWS SDK | Lambda |
| react, react-dom | UI framework | Frontend |
| tailwindcss | Utility-first CSS (v4) | Frontend |
| jose | JWT handling in browser | Frontend |
| dompurify | Sanitizing untrusted strings | Frontend |
| qrcode.react | Device-pairing QR codes | Frontend |

Python deps are pinned exactly (`==`) with `uv.lock` committed in both `lambda/` and `tools/`. Renovate (`.github/renovate.json5`) raises bumps, including a regex manager over `lib/config.ts`.

## Gotchas

### Python/Lambda

- **Decorated inner handlers MUST be `-> Response[Any]`, never bare `-> Response`.** All routers use `enable_validation=True`, so powertools feeds the return annotation to pydantic; a bare `Response` raises `PydanticSchemaGenerationError` on first request. The abstract `BaseRoute.handle()` keeps un-parameterised `-> Response` because it is never decorated.

<a name="pep-758-except-clauses-are-not-syntax-errors"></a>
- **`except A, B:` without parentheses is valid PEP 758 syntax**, used in ~16 places (`shared/utils.py`, `middlewares/hawk_auth.py`, `services/hawk_service.py`, `routes/collections/read.py`, …). **Do NOT "fix" it by adding parentheses** — Black targets py314 and normalizes them back off. Any tool on an older interpreter (system `python3` is 3.12) reports a false syntax error on valid code. Verify with `uv run python -c "import ast; ast.parse(open(F).read())"`.
- **Type-only `types_boto3_*` imports MUST be under `if TYPE_CHECKING:`** with the annotation quoted. `types-boto3` is dev-only, so a module-level import raises `ImportError` in the deployed Lambda. Only the `apigatewaymanagementapi`, `dynamodb` and `kms` extras are installed — touching a new AWS service means adding its extra, or mypy fails with `import-not-found`.
- **DynamoDB item values are a 13-member union** under the real stubs. Cast at the extraction boundary — `item = cast(dict[str, Any], response["Item"])` — rather than weakening the `Table` type or suppressing. This keeps the Table API checked while item values stay dynamic.
- **TTL is not an access check.** DynamoDB TTL deletion lags by up to 48 h, so every read of an ephemeral item *also* re-checks `expiry` in code and treats an expired item as absent — 6 sites do this (`fxa_token_manager.py:118,204,245,325`, `oauth_code_manager.py:86,146`). A new ephemeral item type MUST do both; relying on TTL alone leaves expired sessions valid for up to two days.
- **Never use `table.scan()` for user-scoped storage operations.** Use the `UserCollectionsIndex` GSI via `list_collections(user_id)`. One exception exists and should not be copied: `DeviceManager.get_devices` scans the auth table (which has no GSI — `UserCollectionsIndex` is the only GSI in the stack) *and* does not paginate, so device lists truncate past 1 MB of auth-table data.
- **Always paginate `table.query()`**: DynamoDB returns at most 1 MB per call. Follow `LastEvaluatedKey` in a loop (see `list_collections`) or results are silently truncated.
- **Atomic metadata updates**: use `update_item` with `ADD` for count/usage on existing collections — never `put_item`, which is a read-modify-write race.
- **BSO usage delta**: when updating a BSO, fetch the existing object first (`get_storage_object`) to compute `new_len - old_len`.
- **mypy narrowing**: use `if x is not None:` directly. A derived boolean (`found = x is not None; if found: x.attr`) is not tracked and produces `union-attr`.
- **Hawk auth**: unified `HawkAuthMiddleware` handles storage (router-level) and session (per-route via `middlewares=[...]` on the route class). No separate Lambda authorizer.
- **Exception handlers**: router-level handlers format auth errors — `HawkAuthenticationError` → 401, `UidMismatchError` → 403.
- **Coverage exclusions**: `pragma: nocover`, `__repr__`, `TYPE_CHECKING`, abstract methods, `*/generated/*`.
- **HAWK credentials** expire after 300 s; clients refresh via the Token API.

### TypeScript/CDK

- **`cdk synth` needs Docker with buildx** (Lambda bundling builds an image from `docker/bundling/Dockerfile` with hardcoded `type=gha` BuildKit cache flags) **and** a prior `./gradlew smithyBuild` — `buildOpenApiSpec` does a synth-time `readFileSync` of `build/smithy/<service>/openapi/<Service>Service.openapi.json` and throws ENOENT without it.
- **REST integrations are wired by string substitution**, not CDK constructs: `smithy/models/main.smithy` carries `CDK_LAMBDA_FUNCTION_ARN`, `CDK_API_ROLE_ARN`, `CDK_CORS_ORIGIN` placeholders that `buildOpenApiSpec` regex-replaces. Renaming a placeholder silently breaks the integration.
- **All tables have `deletionProtection: true` and `RETAIN_ON_UPDATE_OR_DELETE`.** Never change a `tableName`, partition key, or sort key — CloudFormation treats it as a replacement, orphans the old table, and the new one starts empty.
- **`...DEFAULT_TABLE_PROPS` is spread LAST** in every table literal (`service.ts:191, 221, 236, 250, 413`), so a per-table override of the four props it sets (`billingMode`, `encryption`, `removalPolicy`, `deletionProtection`) is silently discarded. Change the shared const, or move the spread above your override.
- **The Profile Lambda has read-only access to the auth table** (`grantReadData`, `service.ts:401`) while Auth has `grantReadWriteData`. Any write added to a Profile route fails at runtime with `AccessDeniedException`, and tests cannot catch it because DynamoDB is stubbed.
- **New monitored resources** must be exposed as `public readonly` on `ServiceStack`, threaded through `app.ts`, and added to `MonitoringStackProps`.
- **Output**: CloudFormation templates go to `build/cdk.out`.

### AWS Services

- **DynamoDB**: PAY_PER_REQUEST; TTL attribute is `expiry` (not `ttl`); `ffsync-storage-*` has no TTL configured.
- **Lambda**: ARM64, Python 3.14.
- **KMS**: RSA-2048 for signing self-signed JWTs; Token and Profile call `GetPublicKey` to verify.

### Smithy

- **Build**: `./gradlew smithyBuild` from `smithy/` after any model change. Output lands in the **repo-root** `build/smithy`, not under `smithy/`.
- **Projections**: `storage`, `auth`, `token`, `profile` — lowercase, one per service shape. The name MUST stay the lowercased service name: both CDK and `codegen.sh` derive paths from it.
- **The Channel API is not modelled in Smithy** — it is pure CDK.
- **Do not trust generated docstrings on units.** `smithy/models/storage/bso.smithy:27` documents BSO `modified` as "milliseconds since epoch"; the code uses **seconds** (`get_current_timestamp()` = `round(time.time(), 2)`). The wrong description propagates into the generated model. The IDL is the bug, not the code.
- **A stale `generated/` is invisible to every gate.** It imports, type-checks, lints and passes all 958 tests, because nothing compares it against the IDL: there is no pre-commit hook, no checksum, no CI step diffing regenerated output, and no committed copy to diff against (the directory is git-ignored). CI regenerates from a clean checkout, so it is always correct-by-construction and structurally blind to local drift. The drift observed in Sept 2026 was cosmetic (a relocated unused model, a dropped field description), but nothing would have caught a renamed field or a changed constraint either. **Re-run `./scripts/codegen.sh` after pulling or after any IDL change.**

## Testing

```bash
cd lambda
./scripts/codegen.sh          # required on a fresh clone / after IDL changes
uv run pytest                 # baseline: 958 passed, 100.00% coverage, ~40s
uv run pytest -k test_bso     # specific pattern
uv run pytest -n 0            # serial, for pdb
```

- **Route tests pass real event objects**: `route.handle(APIGatewayProxyEvent(event_dict))`, never a bare dict.
- **Read responses through the helpers**: `json_body(response)` and `header(response, name)` from `tests/conftest.py` — never `json.loads(response.body)` (powertools types `body` as `Optional[str]` and headers as `str | list[str]`).
- **Test structure is a loose mirror, not strict.** `src/routes/{bso,collections,info}` and the storage root are covered by grouped files (`tests/routes/test_bso_routes.py`, `test_collection_routes.py`, `test_info_routes.py`, `test_storage_routes.py`); `src/routes/{auth,profile,storage,token}` mirror one file per route.
- **Fixtures**: `mock_service_provider`, `mock_storage_manager` in `tests/conftest.py`. Boto fixtures (`dynamodb_stubber`, `dynamodb_table`, `kms_stubber`, `apigw_stubber`, `boto_session`) live in `tests/fixtures/boto.py`, which conftest star-imports — so those are globally available. `tests/fixtures/integration.py` is **not** star-imported: import its helpers by name (`from tests.fixtures.integration import build_hawk_auth_header, build_storage_event`). Shared bare-`MagicMock` auth-route doubles live in `tests/routes/auth/conftest.py` — keep them bare, since adding setup there silently changes every consumer.
- **DynamoDB stubber format**: `add_response()` expects wire format (`{"S": ...}`, `{"N": ...}`); the resource layer deserializes. Pass `None` as the third argument to skip expected-params validation.
- **100% coverage** is enforced via `--cov-fail-under=100`. Reports: terminal, `htmlcov/`, `coverage.xml`.

## CI/CD

Eight workflows in `.github/workflows/`:

| Workflow | Trigger | Does |
|---|---|---|
| `lambda-tests.yml` | `lambda/**` | Java 17 + `gradlew smithyBuild` → Python 3.14 + uv → `codegen.sh` → **black → isort → flake8 → mypy → pytest** |
| `build.yml` | reusable | smithy build → frontend build → `cdk synth` |
| `cdk-diff.yml` | PRs to `lib/`, `lambda/`, `smithy/`, CDK config | reuses `build.yml`, diffs prod; destructive changes warn but do not fail |
| `deploy.yml` | **push to `mainline`** | `cdk deploy *-prod GitHubOidcStack --require-approval never` |
| `frontend-build.yml` | `frontend/**` | Node 24, `npm ci` → `npm test` → `npm run build` |
| `codeql.yml` | push/PR + weekly cron | actions, javascript-typescript, python |
| `code-review.yml` | PRs touching `**.ts`/`**.py`/`**.smithy` | Claude Code on Bedrock |
| `code-scan.yml` | — | security scanning |

**Every push to `mainline` deploys to production.** The only gate is the `prod` GitHub environment.

The CI check order matters: codegen runs *before* the Python checks, because `src/shared/models.py` cannot import without it.

## Tools

`tools/` is uv-managed and requires Python >=3.14 (`tools/README.md` still says `pip install -r requirements.txt`, which no longer exists):

```bash
cd tools && uv sync
uv run python ffsync_client.py info collections
```

### ffsync_client.py
Click CLI for the Storage API, signing with `requests-hawk`.

- `info collections|counts|usage|quota`
- `collection list|create|get|delete`
- `bso get|update|delete`
- `storage delete-all`

**Trap**: `--credentials-file` hardcodes a beta host and overwrites `--api-endpoint` / `HAWK_API_ENDPOINT`, so any credentials-file invocation talks to beta regardless of flags. Use `HAWK_ID` / `HAWK_KEY` / `HAWK_API_ENDPOINT` env vars to target another stage.

### get_hawk_token.py
Obtains HAWK credentials via the OIDC flow.

```bash
uv run python get_hawk_token.py \
  --issuer https://auth.example.com/application/o/myapp/ \
  --client-id my-client-id \
  --token-server-url https://sync.example.com \
  --json-only > hawk_creds.json
```

## Domain Model

| Concept | Description |
|---------|-------------|
| **BSO** | Basic Storage Object: `id`, `payload` (JSON string), `modified` (epoch seconds), optional `sortindex`. `ttl` is write-only (`BSOInput`), stored as an absolute `expiry` attribute, never echoed back. |
| **Collection** | Named group of BSOs ("bookmarks", "tabs", "history", "passwords") |
| **User** | Identified by OIDC subject claim; storage isolated per user |
| **HAWK** | HTTP auth scheme used by Firefox Sync clients |
| **Device** | FxA device record: `id`, `name`, `type`, `pushCallback`/`pushPublicKey`/`pushAuthKey`, `availableCommands`, `sessionTokenId`, `createdAt`/`lastAccessTime` in **milliseconds**. Keyed `DEVICE#{uid}#{device_id}`. Endpoints are implemented, not stubs. |
| **Channel** | Short-lived WebSocket pairing channel: `channelId`, up to 3 connections, up to 10 messages, 300 s TTL |

## In-Package Resources

| Resource | Path | Use For |
|----------|------|---------|
| Lambda README | `lambda/README.md` | Python setup, API endpoints |
| Tools README | `tools/README.md` | CLI usage (note: install steps are stale) |
| Smithy Models | `smithy/models/` | API contract definitions |
| CDK Stacks | `lib/stacks/` | Infrastructure definitions |
| Python Config | `lambda/pyproject.toml` | pytest, black, isort, flake8, mypy settings |
| CDK Config | `cdk.json` | CDK app config, context, output directory |
| Frontend config | `frontend/package.json`, `frontend/vite.config.ts` | `frontend/README.md` is an unmodified Vite starter — use these instead |

## References

- [README](./README.md)
- [Lambda README](./lambda/README.md)
- [Tools README](./tools/README.md)
- [Firefox Sync Protocol](https://mozilla-services.readthedocs.io/en/latest/storage/apis-1.5.html)
