# ffsync

A self-hosted Mozilla Firefox Sync server built on AWS serverless infrastructure.
It implements the [Firefox Sync 1.5 storage API](https://mozilla-services.github.io/syncstorage-rs/api.html) and an FxA-compatible auth server so that Firefox and Firefox-compatible clients can sync bookmarks, history, passwords, and other data to your own AWS account.

## Architecture

```
Firefox Client
      │
      ├── OIDC login ──→ Auth API  ─ auth.<stage>.ffsync.layertwo.dev
      │                    ├── DynamoDB (auth sessions, OAuth state)
      │                    ├── KMS (RSA-2048, signs OAuth JWTs)
      │                    └── Handles: account, OAuth, OIDC, sessions
      │
      ├── JWT Bearer ──→ Token API  ─ token.<stage>.ffsync.layertwo.dev
      │                    ├── DynamoDB (token-users, token-cache)
      │                    └── Exchanges JWT for HAWK credentials (300s TTL)
      │
      ├── JWT Bearer ──→ Profile API  ─ profile.<stage>.ffsync.layertwo.dev
      │                    ├── DynamoDB (auth, read-only)
      │                    └── Returns user profile (email, uid, locale)
      │
      └── HAWK auth ───→ Storage API  ─ storage.<stage>.ffsync.layertwo.dev
                           ├── DynamoDB (collections & BSOs)
                           │     └── GSI: UserCollectionsIndex
                           └── HawkAuthMiddleware validates inline

CloudFront  ─ <stage>.ffsync.layertwo.dev
      └── S3 Bucket  ─ frontend SPA + /.well-known/fxa-client-configuration

CDK Stacks (TypeScript / AWS CDK):
  lib/stacks/service.ts      ─ 4 Lambdas + 4 API Gateways + DynamoDB + KMS
  lib/stacks/frontend.ts     ─ CloudFront + S3 frontend deployment
  lib/stacks/monitoring.ts   ─ CloudWatch dashboard & alarms
  lib/stacks/github-oidc.ts  ─ GitHub Actions OIDC role for CI/CD
```

## Prerequisites

- [Node.js](https://nodejs.org/) 18+
- [Python](https://www.python.org/) 3.14+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- [AWS CDK CLI](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html): `npm install -g aws-cdk`
- AWS credentials configured (`aws configure` or environment variables)
- An OIDC provider (e.g. Keycloak, Auth0, or AWS Cognito) for user authentication

## Deployment

### 1. Install dependencies

```bash
npm install                    # CDK & TypeScript toolchain
cd lambda && uv pip install --group dev . && cd ..
```

### 2. Bootstrap CDK (first time per account/region)

```bash
cdk bootstrap aws://<ACCOUNT_ID>/<REGION>
```

### 3. Create SSM Parameters (first time per stage)

The OIDC provider URL and client ID are stored as SSM Parameters, created outside of CDK:

```bash
aws ssm put-parameter --name /ffsync/prod/oidc-provider-url \
  --value "https://your-oidc-provider/application/o/firefox-sync/" \
  --type String

aws ssm put-parameter --name /ffsync/prod/client-id \
  --value "your-oauth-client-id" \
  --type String
```

### 4. Synthesize and deploy

```bash
cdk synth    # verify the CloudFormation template renders cleanly
cdk deploy   # deploy all stacks to your AWS account
```

The frontend `config.json` is generated automatically at deploy time from SSM Parameters and cross-stack references.

### 5. Point Firefox at your server

In `about:config` set:

```
identity.fxaccounts.autoconfig.uri = https://<stage>.ffsync.layertwo.dev
```

Firefox will auto-discover the auth, token, profile, and storage server URLs from `/.well-known/fxa-client-configuration`.

## Configuration Reference

| Variable | Description | Default |
|---|---|---|
| `BASE_DOMAIN` | Root domain for the API Gateway custom domain | required |
| `OIDC_PROVIDER_URL` | OIDC provider URL (from SSM Parameter at deploy time) | required |
| `OIDC_CLIENT_ID` | OAuth client ID (from SSM Parameter at deploy time) | required |
| `STORAGE_TABLE_NAME` | DynamoDB table for BSO/collection storage | set by CDK |
| `TOKEN_USERS_TABLE_NAME` | DynamoDB table for token-to-user mapping | set by CDK |
| `TOKEN_CACHE_TABLE_NAME` | DynamoDB table for HAWK credential caching | set by CDK |
| `AUTH_TABLE_NAME` | DynamoDB table for auth sessions and OAuth state | set by CDK |
| `AUTH_SIGNING_KEY_ID` | KMS key ID for signing OAuth JWTs | set by CDK |
| `CLOCK_SKEW_TOLERANCE` | Seconds of clock skew tolerated in OIDC JWT validation | `300` |
| `OIDC_CACHE_TTL_SECONDS` | OIDC provider config and JWKS cache TTL in seconds | `3600` |
| `HAWK_TIMESTAMP_SKEW_TOLERANCE` | HAWK timestamp tolerance in seconds | `60` |
| `RETRY_AFTER_SECONDS` | Value for `Retry-After` header on 503 responses | `30` |
| `TOKEN_DURATION` | HAWK token lifetime in seconds | `300` |

## Development

### Run tests

```bash
cd lambda
pytest                    # all tests (parallel, 100% coverage required)
pytest -k test_read_bso   # specific test pattern
pytest -n 0               # without parallel execution
```

### Lint & format

```bash
# TypeScript (CDK)
npm run check-format      # check formatting
npm run format            # auto-fix formatting

# Python (Lambda)
cd lambda
black src/ tests/         # format
isort src/ tests/         # sort imports
flake8 src/ tests/        # lint
mypy                      # type check
```

### Frontend

```bash
cd frontend
npm install
npm run dev               # local dev server
npm run build             # production build
```

## License

See [LICENSE](LICENSE).
