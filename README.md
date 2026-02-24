# ffsync

A self-hosted Mozilla Firefox Sync server built on AWS serverless infrastructure.
It implements the [Firefox Sync 1.5 storage API](https://mozilla-services.github.io/syncstorage-rs/api.html) so that Firefox and Firefox-compatible clients can sync bookmarks, history, passwords, and other data to your own AWS account.

## Architecture

```
Firefox Client
      │
      ▼
API Gateway (REST)
      │
      ├── Authorizer Lambda (HAWK / OIDC token validation)
      │
      └── Handler Lambda (Python)
            │
            ├── DynamoDB  ─ collections & BSOs (per-user partition key)
            │     └── GSI: UserCollectionsIndex (user_id → collection metadata)
            └── CloudWatch ─ metrics & alarms (via Monitoring stack)

CloudFront ─ serves frontend SPA from S3
      │
      └── S3 Bucket ─ frontend assets + generated config.json

CDK Stacks (TypeScript / AWS CDK):
  lib/stacks/service.ts     ─ core API Gateway + Lambda + DynamoDB resources
  lib/stacks/frontend.ts    ─ CloudFront + S3 frontend deployment
  lib/stacks/monitoring.ts  ─ CloudWatch dashboard & alarms
```

## Prerequisites

- [Node.js](https://nodejs.org/) 18+
- [Python](https://www.python.org/) 3.12+
- [AWS CDK CLI](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html): `npm install -g aws-cdk`
- AWS credentials configured (`aws configure` or environment variables)
- An OIDC provider (e.g. Keycloak, Auth0, or AWS Cognito) for user authentication

## Deployment

### 1. Install dependencies

```bash
npm install                    # CDK & TypeScript toolchain
cd lambda && pip install -r requirements.txt && cd ..
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
identity.sync.tokenserver.uri = https://<your-api-domain>/token/1.0/sync/1.5
```

## Configuration Reference

| Variable | Description | Default |
|---|---|---|
| `BASE_DOMAIN` | Root domain for the API Gateway custom domain | required |
| `OIDC_PROVIDER_URL` | OIDC provider URL (from SSM Parameter at deploy time) | required |
| `OIDC_CLIENT_ID` | OAuth client ID (from SSM Parameter at deploy time) | required |
| `STORAGE_TABLE_NAME` | DynamoDB table name for BSO/collection storage | set by CDK |
| `TOKEN_USERS_TABLE_NAME` | DynamoDB table for token-to-user mapping | set by CDK |
| `TOKEN_CACHE_TABLE_NAME` | DynamoDB table for token caching | set by CDK |
| `CLOCK_SKEW_TOLERANCE` | Seconds of clock skew tolerated in HAWK auth | `300` |
| `HAWK_TIMESTAMP_SKEW_TOLERANCE` | Additional HAWK timestamp tolerance in seconds | `60` |
| `RETRY_AFTER_SECONDS` | Value for `Retry-After` header on 503 responses | `30` |
| `TOKEN_DURATION` | Token lifetime in seconds | `300` |

## Development

### Run tests

```bash
cd lambda
python -m pytest tests/ -v
```

### Lint

```bash
npm run lint        # ESLint (TypeScript)
cd lambda && ruff check src/
```

## License

See [LICENSE](LICENSE).
