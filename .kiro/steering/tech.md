---
inclusion: always
---

# Tech Stack & Development Guidelines

## Infrastructure (TypeScript)

| Technology | Version | Purpose |
|------------|---------|---------|
| AWS CDK | 2.231+ | Infrastructure as Code |
| CDK Monitoring Constructs | 9.16+ | Observability dashboards/alarms |
| TypeScript | ~5.9 | Strict mode enabled |

### TypeScript Rules
- Target: ES2020, Module: node20
- Strict null checks and implicit any checks enabled
- Use `noImplicitReturns: true` - all code paths must return

## Backend (Python)

| Technology | Purpose |
|------------|---------|
| Python 3.14 | Lambda runtime |
| AWS Lambda Powertools | Logging, APIGatewayRestResolver |
| boto3 | AWS SDK |
| dataclasses-json | Model serialization |
| PyJWT | JWT token handling |
| requests | HTTP client for OIDC |

### Python Rules
- Line length: 100 characters (Black + isort)
- Type hints required on function signatures
- Use `@dataclass` with `dataclasses-json` for models
- Logger: `from aws_lambda_powertools import Logger`

## API Design (Smithy)
- Smithy v1.64 generates OpenAPI specs
- Two services: `StorageService`, `TokenService`
- Run `smithy build` from `smithy/` directory after model changes

## AWS Services
- API Gateway: REST, edge-optimized
- Lambda: ARM64 architecture
- DynamoDB: PAY_PER_REQUEST billing mode
- Secrets Manager: OIDC configuration storage

## Commands

```bash
# Infrastructure (from project root)
npm run build          # Compile TypeScript
npm run cdk synth      # Synthesize CloudFormation
npm run format         # ESLint + Prettier auto-fix

# Lambda (from lambda/ directory)
pytest                 # Run tests (100% coverage required)
pytest -k <pattern>    # Run specific tests
pytest -n auto         # Parallel execution (default)

# API Models (from smithy/ directory)
smithy build           # Generate OpenAPI specs
```

## Code Quality Requirements

### Python (lambda/)
- **100% test coverage** - enforced via `--cov-fail-under=100`
- Black formatter (line-length 100, target py314)
- isort with black profile
- flake8 for linting (E, W, F, C90 rules)
- mypy for type checking
- Use `# pragma: nocover` sparingly for unreachable paths

### TypeScript (lib/)
- ESLint + Prettier enforced
- Prettier plugin sorts imports automatically
- Run `npm run format` before committing

## Testing Conventions

### Python Tests
- Tests mirror source structure: `tests/routes/bso/test_read.py` ↔ `src/routes/bso/read.py`
- Use fixtures from `conftest.py`: `mock_service_provider`, `mock_storage_manager`
- Parallel execution enabled by default (`-n auto`)

### Coverage Exclusions
Automatically excluded from coverage:
- `pragma: nocover` comments
- `__repr__` methods
- `TYPE_CHECKING` blocks
- Abstract methods
