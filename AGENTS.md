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
| Build System | npm (CDK), pytest (Lambda) |
| Languages | TypeScript (CDK), Python 3.14 (Lambda) |
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
| Type check Lambda | `mypy src/ tests/` | `lambda/` directory |
| Build Smithy | `smithy build` | `smithy/` directory |

## Architecture

```
Firefox Client
    ↓ OIDC Bearer Token
Token Service (Lambda) → Secrets Manager (OIDC config)
    ↓ HAWK credentials (300s TTL)
Storage Service (Lambda) → DynamoDB (BSOs)
    ↑ API Gateway (REST)
```

**Two Lambda Functions:**
- **Token Service** (`lambda/src/entrypoint/token_api.py`): Exchanges OIDC tokens for HAWK credentials
- **Storage Service** (`lambda/src/entrypoint/storage_api.py`): REST API for Firefox Sync data (BSOs)

**HAWK Authorizer** (`lambda/src/entrypoint/hawk_authorizer.py`): Lambda authorizer for API Gateway

**Environment Configuration:**
- `CLOCK_SKEW_TOLERANCE`: OIDC JWT validation skew (Token API: 300s)
- `OIDC_CACHE_TTL_SECONDS`: OIDC provider config and JWKS cache TTL (Token API: 3600s / 1 hour)
- `HAWK_TIMESTAMP_SKEW_TOLERANCE`: HAWK timestamp validation skew (60s default)
- `TOKEN_DURATION`: HAWK credential duration (300s)

## Project Structure

```
lib/                          # CDK infrastructure (TypeScript)
├── app.ts                    # CDK app entrypoint
├── config.ts                 # AWS account/region config
├── stacks/
│   ├── service.ts            # Main service stack (Lambda, API Gateway, DynamoDB)
│   ├── monitoring.ts         # CloudWatch dashboards and alarms
│   └── pipeline.ts           # CDK Pipelines for CI/CD

lambda/                       # Python Lambda functions
├── src/
│   ├── entrypoint/           # Lambda handlers (token_api, storage_api, hawk_authorizer)
│   ├── routes/               # API route handlers (bso, collections, info, storage, token)
│   ├── services/             # Business logic (storage_manager, user_manager, oidc_validator)
│   ├── shared/               # Shared utilities (models, exceptions, base_route)
│   └── environment/          # Dependency injection (service_provider)
├── tests/                    # Mirror structure of src/
├── pyproject.toml            # Python tooling config (pytest, black, isort, flake8, mypy)
└── requirements.txt          # Production dependencies

smithy/                       # API contract definitions
└── models/                   # Smithy models (storage, token, errors)

tools/                        # CLI tools for testing
├── ffsync_client.py          # HAWK-authenticated API client
└── get_hawk_token.py         # OIDC → HAWK credential exchange
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
- **Service layer**: Business logic in `services/` (storage_manager, user_manager)

### TypeScript (CDK)
- **Target**: ES2020, Module: node20
- **Strict mode**: Enabled (null checks, implicit any checks)
- **Return values**: All code paths must return (`noImplicitReturns: true`)
- **Imports**: Auto-sorted by Prettier plugin
- **CDK profile**: `ffsync` (set in `cdk.json`)

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
| cryptography | HAWK authentication (implemented directly) | Lambda |
| boto3 | AWS SDK (DynamoDB, Secrets Manager) | Lambda |

## Gotchas

### Python/Lambda
- **Parallel tests**: Default (`-n auto`) - use fixtures from `conftest.py` for isolation
- **Coverage exclusions**: `pragma: nocover`, `__repr__`, `TYPE_CHECKING`, abstract methods
- **HAWK credentials**: Expire after 300 seconds - clients must refresh via Token Service
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

### AWS Services
- **DynamoDB**: PAY_PER_REQUEST billing - no capacity planning needed
- **Lambda**: ARM64 architecture for cost optimization
- **API Gateway**: REST API, edge-optimized

### Smithy
- **Version**: 1.64
- **Build**: Run `smithy build` from `smithy/` directory after model changes
- **Output**: Generates OpenAPI specs for documentation

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
- GitHub Actions runs tests on Python 3.13 and 3.14
- Triggers on changes to `lambda/**` or workflow file
- Uses pip cache for faster builds

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
| Smithy Models | `smithy/models/` | API contract definitions |
| CDK Stacks | `lib/stacks/` | Infrastructure definitions |
| Python Config | `lambda/pyproject.toml` | pytest, black, isort, flake8, mypy settings |
| CDK Config | `cdk.json` | CDK app config, context, output directory |

## References

- [README](./README.md)
- [Lambda README](./lambda/README.md)
- [Tools README](./tools/README.md)
- [Firefox Sync Protocol](https://mozilla-services.readthedocs.io/en/latest/storage/apis-1.5.html)
