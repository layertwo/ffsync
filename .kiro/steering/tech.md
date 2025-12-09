# Tech Stack

## Infrastructure (TypeScript)
- **AWS CDK** (v2.231+) - Infrastructure as Code
- **CDK Monitoring Constructs** - Observability
- **TypeScript** (~5.9) with strict mode enabled

## Backend (Python)
- **Python 3.14** - Lambda runtime
- **AWS Lambda Powertools** - Logging, typing utilities
- **aws-lambda-proxy** - API routing
- **boto3** - AWS SDK
- **dataclasses-json** - JSON serialization for models
- **PyJWT** - JWT token handling
- **requests** - HTTP client for OIDC

## API Design
- **Smithy** (v1.64) - API modeling language
- Generates OpenAPI specs for API Gateway REST APIs
- Two services: `StorageService` and `TokenService`

## AWS Services
- API Gateway (REST, edge-optimized)
- Lambda (ARM64 architecture)
- DynamoDB (PAY_PER_REQUEST billing)
- Secrets Manager (OIDC configuration)
- Route 53 (DNS)
- ACM (TLS certificates)

## Common Commands

```bash
# CDK/Infrastructure
npm run build          # Compile TypeScript
npm run cdk synth      # Synthesize CloudFormation
npm run cdk deploy     # Deploy stacks
npm run format         # Run ESLint with auto-fix

# Python/Lambda (run from lambda/ directory)
pytest                 # Run tests with coverage (100% required)
pytest -k <pattern>    # Run specific tests

# Smithy (requires smithy-cli)
smithy build           # Generate OpenAPI specs from models
```

## Code Quality
- **ESLint + Prettier** for TypeScript
- **Black** (line-length 100) for Python formatting
- **isort** for Python imports
- **pytest** with 100% coverage requirement
- **flake8** for Python linting
