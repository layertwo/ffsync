# Agent Context for ffsync

This file provides context for AI coding agents working on this repository. It contains build commands, conventions, and gotchas to help agents work effectively.

> RFC 2119: MUST = required, SHOULD = recommended, MAY = optional

## Critical Rules

**MUST update this file when:** corrected about how something works, or user says "remember this"

**MUST update README.md when:** functionality or setup steps change

## Package Overview

| Field | Value |
|-------|-------|
| Package | @layertwo/ffsync |
| Build System | npm (CDK), pytest (Lambda), Gradle (Smithy), Vite (Frontend) |
| Languages | TypeScript (CDK + Frontend), Python 3.14 (Lambda) |
| Runtime | AWS Lambda (ARM64) |
| Purpose | Self-hosted Firefox Sync protocol implementation on AWS |

## Quick Commands

| Task | Command | Location |
|------|---------|----------|
| Build CDK | `npm run build` | Project root |
| CDK Synth | `npm run cdk synth` | Project root |
| Format CDK | `npm run format` | Project root |
| Test Lambda | `pytest` | `lambda/` directory |
| Test Lambda (parallel) | `pytest -n auto` | `lambda/` directory |
| Test specific pattern | `pytest -k <pattern>` | `lambda/` directory |
| Format Lambda | `black src/ tests/ && isort src/ tests/` | `lambda/` directory |
| Lint Lambda | `flake8 src/ tests/` | `lambda/` directory |
| Type check Lambda | `mypy` | `lambda/` directory |
| Build Smithy | `./gradlew smithyBuild` | `smithy/` directory |
| Frontend dev | `npm run dev` | `frontend/` directory |
| Frontend build | `npm run build` | `frontend/` directory |

## Architecture

```
Firefox Client
    │
    ├─ OIDC login → Auth API → DynamoDB (auth) + KMS (JWT signing)
    │                  ├─ FxA-compatible auth (account, OAuth, OIDC, sessions)
    │                  └─ Issues self-signed JWTs for token/profile servers
    │
    ├─ JWT Bearer → Token API → DynamoDB (token-users, token-cache)
    │                  └─ Exchanges JWT for HAWK credentials (300s TTL)
    │
    ├─ JWT Bearer → Profile API → DynamoDB (auth, read-only)
    │                  └─ Returns user profile (email, uid, locale)
    │
    └─ HAWK auth → Storage API → DynamoDB (storage BSOs)
                       └─ HawkAuthMiddleware validates inline (no separate authorizer)

CloudFront → S3 (frontend SPA + /.well-known/fxa-client-configuration)
```

**Four Lambda Functions:**
- **Auth API** (`lambda/src/entrypoint/auth_api.py`): FxA-compatible auth server — account, login, OAuth, OIDC, sessions
- **Token API** (`lambda/src/entrypoint/token_api.py`): Exchanges self-signed JWTs for HAWK credentials
- **Profile API** (`lambda/src/entrypoint/profile_api.py`): Returns user profile via OAuth Bearer auth
- **Storage API** (`lambda/src/entrypoint/storage_api.py`): REST API for Firefox Sync data (BSOs)

**Four API Gateways (SpecRestApi, edge-optimized):**
- **Auth API**: `auth.<stage>.<BASE_DOMAIN>` — mixed auth (authPW, session Hawk, OAuth Bearer)
- **Token API**: `token.<stage>.<BASE_DOMAIN>` — OAuth Bearer (self-signed JWT)
- **Profile API**: `profile.<stage>.<BASE_DOMAIN>` — OAuth Bearer (self-signed JWT)
- **Storage API**: `storage.<stage>.<BASE_DOMAIN>` — HAWK auth (inline middleware)

**Four DynamoDB Tables:**
- `ffsync-storage-<stage>` — BSOs and collection metadata (GSI: `UserCollectionsIndex`)
- `ffsync-token-users-<stage>` — token-to-user mapping
- `ffsync-token-cache-<stage>` — HAWK credential cache (TTL-enabled)
- `ffsync-auth-<stage>` — auth sessions and OAuth state (TTL-enabled)

**Environment Configuration:**
- `CLOCK_SKEW_TOLERANCE`: OIDC JWT validation skew (Auth API: 300s)
- `OIDC_CACHE_TTL_SECONDS`: OIDC provider config and JWKS cache TTL (Auth API: 3600s)
- `HAWK_TIMESTAMP_SKEW_TOLERANCE`: HAWK timestamp validation skew (60s)
- `TOKEN_DURATION`: HAWK credential duration (300s)
- `RETRY_AFTER_SECONDS`: `Retry-After` header value on 503 responses (30s)
- `AUTH_TABLE_NAME`: Auth DynamoDB table name (set by CDK)
- `AUTH_SIGNING_KEY_ID`: KMS key ID for signing OAuth JWTs (set by CDK)
- `STORAGE_TABLE_NAME`: Storage DynamoDB table name (set by CDK)
- `TOKEN_USERS_TABLE_NAME`: Token-users DynamoDB table name (set by CDK)
- `TOKEN_CACHE_TABLE_NAME`: Token-cache DynamoDB table name (set by CDK)

## Project Structure

```
lib/                          # CDK infrastructure (TypeScript)
├── app.ts                    # CDK app entrypoint
├── config.ts                 # AWS account/region config
├── config/service.ts         # Service enum (AUTH, TOKEN, PROFILE, STORAGE)
├── utils.ts                  # Helper utilities
├── stacks/
│   ├── service.ts            # Main service stack (Lambda, API Gateway, DynamoDB, KMS)
│   ├── frontend.ts           # CloudFront + S3 frontend deployment
│   ├── github-oidc.ts        # GitHub Actions OIDC role for CI/CD
│   └── monitoring.ts         # CloudWatch dashboards and alarms

frontend/                     # React SPA (Vite + Tailwind)
├── src/                      # React components and pages
├── index.html                # Entry point
├── vite.config.ts            # Vite configuration
└── package.json              # Dependencies (React 19, Tailwind v4, react-router)

lambda/                       # Python Lambda functions
├── src/
│   ├── entrypoint/           # Lambda handlers (auth_api, token_api, profile_api, storage_api)
│   ├── middlewares/          # Request middleware
│   │   ├── hawk_auth.py      # Unified Hawk auth (storage + session, per-route or router-level)
│   │   ├── request_logging.py # Request/response logging
│   │   └── weave_timestamp.py # X-Weave-Timestamp header
│   ├── routes/               # API route handlers
│   │   ├── auth/             # FxA-compatible auth (account, OAuth, OIDC, sessions)
│   │   ├── bso/              # BSO CRUD operations
│   │   ├── collections/      # Collection management
│   │   ├── info/             # Storage info endpoints (counts, usage, quota)
│   │   ├── profile/          # Profile endpoint (OAuth Bearer auth)
│   │   ├── storage/          # Storage-level operations (delete all)
│   │   └── token/            # Token request handling
│   ├── services/             # Business logic
│   │   ├── api_router.py     # Route dispatch + exception handlers
│   │   ├── storage_manager.py
│   │   ├── user_manager.py
│   │   ├── hawk_service.py
│   │   ├── oidc_validator.py
│   │   ├── jwt_service.py
│   │   ├── jwt_verifier.py
│   │   ├── auth_account_manager.py
│   │   ├── fxa_crypto.py
│   │   ├── fxa_token_manager.py
│   │   ├── oauth_code_manager.py
│   │   └── token_generator.py
│   ├── shared/               # Shared utilities (models, exceptions, base_route)
│   └── environment/          # Dependency injection (service_provider)
├── tests/                    # Mirror structure of src/
└── pyproject.toml            # Python dependencies and tooling config (pytest, black, isort, flake8, mypy)

smithy/                       # API contract definitions (Gradle-based)
├── models/                   # Smithy models (StorageService, AuthService, TokenService, ProfileService)
├── build.gradle.kts          # Gradle build file
└── smithy-build.json         # OpenAPI generation config (4 projections)

tools/                        # CLI tools for testing
├── ffsync_client.py          # HAWK-authenticated API client
├── ffsync_hawk_client.py     # HAWK client using mohawk library
├── get_hawk_token.py         # OIDC → HAWK credential exchange
├── requirements.txt          # Tool dependencies
└── README.md                 # CLI usage documentation
```

## Key Conventions

### Python (Lambda)
- **Line length**: 100 characters (enforced by Black)
- **Type hints**: Required on all function signatures
- **Models**: Use `@dataclass` with `dataclasses-json` for serialization
- **Logging**: `from aws_lambda_powertools import Logger`
- **Testing**: 100% coverage required (`--cov-fail-under=100`)
- **Parallel tests**: Default (`-n auto`), use fixtures for isolation
- **Route structure**: `routes/{resource}/{action}.py` (e.g., `routes/bso/read.py`)
- **Service layer**: Business logic in `services/` (storage_manager, user_manager, etc.)

### TypeScript (CDK)
- **Target**: ES2020, Module: node20
- **Strict mode**: Enabled (null checks, implicit any checks)
- **Return values**: All code paths must return (`noImplicitReturns: true`)
- **Imports**: Auto-sorted by Prettier plugin
- **CDK profile**: `ffsync` (set in `cdk.json`)

### Frontend (React)
- **Framework**: React 19 + Vite + Tailwind CSS v4
- **Routing**: react-router v7
- **Build**: `tsc -b && vite build`

### API Design
- **Timestamps**: Epoch seconds with 2 decimal places (e.g., `1702345678.12`)
- **Authentication**: OIDC Bearer → HAWK credentials (300s duration)
- **Headers**: `X-Last-Modified`, `X-If-Unmodified-Since` for optimistic concurrency
- **Error codes**: 400 (validation), 401 (auth), 409 (conflict), 412 (precondition), 413 (too large), 507 (quota)

## Key Dependencies

| Dependency | Purpose | Layer |
|------------|---------|-------|
| aws-cdk-lib | Infrastructure as Code | CDK |
| cdk-monitoring-constructs | Observability dashboards/alarms | CDK |
| AWS Lambda Powertools | Logging, APIGatewayRestResolver | Lambda |
| dataclasses-json | Model serialization | Lambda |
| PyJWT | JWT token handling | Lambda |
| mohawk | HAWK authentication | Lambda |
| cryptography | Cryptographic operations | Lambda |
| requests | HTTP client (OIDC discovery) | Lambda |
| boto3 | AWS SDK (DynamoDB, KMS) | Lambda |
| react, react-dom | UI framework | Frontend |
| tailwindcss | Utility-first CSS | Frontend |
| jose | JWT handling in browser | Frontend |

## Gotchas

### Python/Lambda
- **Parallel tests**: Default (`-n auto`) - use fixtures from `conftest.py` for isolation
- **Coverage exclusions**: `pragma: nocover`, `__repr__`, `TYPE_CHECKING`, abstract methods
- **HAWK credentials**: Expire after 300 seconds - clients must refresh via Token Service
- **Hawk auth**: Unified `HawkAuthMiddleware` handles both storage (router-level) and session (per-route) Hawk auth. No separate Lambda authorizer.
- **Per-route middleware**: Auth routes opt into session Hawk via `middlewares=[session_hawk]` in `BaseRoute`. Routes that don't need Hawk have no middleware.
- **Exception handlers**: Router-level exception handlers format auth errors. `HawkAuthenticationError` → 401, `UidMismatchError` → 403.
- **Test structure**: Must mirror `src/` structure (e.g., `tests/routes/bso/test_read.py` ↔ `src/routes/bso/read.py`)
- **Fixtures**: Use `mock_service_provider`, `mock_storage_manager` from `conftest.py`
- **DynamoDB GSI**: `list_collections` uses `UserCollectionsIndex` GSI for efficient queries — collection metadata items include `user_id` attribute
- **Never use `table.scan()` for user-scoped operations**: Scans read the entire table. Always use the GSI via `list_collections(user_id)` to query a single user's collections.
- **Always paginate `table.query()` calls**: DynamoDB returns at most 1 MB per call. Follow `LastEvaluatedKey` in a loop (see `list_collections` for the pattern) or results will be silently truncated.
- **Atomic metadata updates**: Use `update_item` with `ADD` for count/usage fields on existing collections — never `put_item`, which creates a read-modify-write race condition.
- **BSO usage delta**: When updating a BSO in an existing collection, fetch the existing object first (`get_storage_object`) to compute the accurate usage delta (`new_len - old_len`).
- **mypy type narrowing**: Use `if x is not None:` directly to narrow `Optional[T]` types. Derived boolean flags (`found = x is not None; if found: x.attr`) are not tracked by mypy and produce `union-attr` errors.
- **DynamoDB stubber format**: `dynamodb_stubber.add_response()` expects DynamoDB wire format (`{"S": "...", "N": "..."}`) for response bodies — the resource layer auto-deserializes. Pass `None` as the third argument to skip expected-params validation.

### TypeScript/CDK
- **Strict mode**: All code paths must return values
- **CDK profile**: Uses `ffsync` profile from `cdk.json`
- **Output**: CloudFormation templates go to `build/cdk.out`
- **API specs**: OpenAPI specs generated by Smithy are loaded inline by `SpecRestApi`

### AWS Services
- **DynamoDB**: PAY_PER_REQUEST billing - no capacity planning needed
- **Lambda**: ARM64 architecture, Python 3.14 runtime
- **API Gateway**: Four REST APIs (auth, token, profile, storage), edge-optimized
- **KMS**: RSA-2048 key for signing OAuth JWTs

### Smithy
- **Build system**: Gradle (not standalone Smithy CLI)
- **Build**: Run `./gradlew smithyBuild` from `smithy/` directory after model changes
- **Projections**: StorageService, AuthService, TokenService, ProfileService — generates OpenAPI specs for all four
- **Output**: OpenAPI specs consumed by CDK `SpecRestApi`

## Testing

### Python Tests
```bash
cd lambda

# Run all tests (parallel, 100% coverage required)
pytest

# Run specific test pattern
pytest -k test_read_bso

# Run with verbose output
pytest -v

# Run without parallel execution
pytest -n 0
```

### Coverage Requirements
- **100% coverage** enforced via `--cov-fail-under=100`
- Coverage reports: terminal, HTML (`htmlcov/`), XML (`coverage.xml`)
- Use `# pragma: nocover` sparingly for unreachable paths

### CI/CD
- GitHub Actions runs Lambda tests on Python 3.14
- Uses `uv` for fast dependency installation (via `astral-sh/setup-uv`)
- Checks: black, isort, flake8, mypy, pytest (in that order)
- CDK diff runs on PRs affecting `lib/`, `smithy/`, or CDK config files
- Frontend build workflow for `frontend/` changes

## Tools

### ffsync_client.py
CLI for interacting with the Storage API using HAWK authentication.

**Commands:**
- `info collections|counts|usage|quota` - Get storage metadata
- `collection list|create|get|delete` - Manage collections
- `bso get|update|delete` - Manage Basic Storage Objects
- `storage delete-all` - Delete all storage data

**Authentication:**
- `--credentials-file hawk_creds.json` - Load HAWK credentials from file
- Or set env vars: `HAWK_ID`, `HAWK_KEY`, `HAWK_API_ENDPOINT`

### get_hawk_token.py
Obtains HAWK credentials via OIDC authentication flow.

**Usage:**
```bash
python get_hawk_token.py \
  --issuer https://auth.example.com/application/o/myapp/ \
  --client-id my-client-id \
  --token-server-url https://sync.example.com \
  --json-only > hawk_creds.json
```

## Domain Model

| Concept | Description |
|---------|-------------|
| **BSO** | Basic Storage Object: `id`, `payload` (JSON string), `modified` (epoch seconds), optional `sortindex`, optional `ttl` |
| **Collection** | Named group of BSOs (e.g., "bookmarks", "tabs", "history", "passwords") |
| **User** | Identified by OIDC subject claim; storage isolated per user |
| **HAWK** | HTTP authentication scheme used by Firefox Sync clients |

## In-Package Resources

| Resource | Path | Use For |
|----------|------|---------|
| Lambda README | `lambda/README.md` | Python development setup, API endpoints |
| Tools README | `tools/README.md` | CLI tools usage, authentication flow |
| Frontend README | `frontend/README.md` | Frontend development |
| Smithy Models | `smithy/models/` | API contract definitions |
| CDK Stacks | `lib/stacks/` | Infrastructure definitions |
| Python Config | `lambda/pyproject.toml` | pytest, black, isort, flake8, mypy settings |
| CDK Config | `cdk.json` | CDK app config, context, output directory |

## References

- [README](./README.md)
- [Lambda README](./lambda/README.md)
- [Tools README](./tools/README.md)
- [Firefox Sync Protocol](https://mozilla-services.readthedocs.io/en/latest/storage/apis-1.5.html)
