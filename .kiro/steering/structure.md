---
inclusion: always
---

# Project Structure

```
lib/                        # CDK Infrastructure (TypeScript)
├── app.ts                  # CDK app entry point
├── config.ts               # Global config (account, region, domains)
├── config/                 # Service-specific configuration
├── stacks/
│   ├── service.ts          # Main stack (Lambda, DynamoDB, API Gateway)
│   ├── pipeline.ts         # CI/CD pipeline
│   └── monitoring.ts       # CloudWatch dashboards/alarms
└── utils.ts                # Helper functions

lambda/                     # Python Lambda code
├── src/
│   ├── entrypoint/         # Lambda handlers (storage_api.py, token_api.py)
│   ├── environment/        # ServiceProvider (DI container)
│   ├── routes/             # API route handlers by resource
│   │   ├── bso/            # BSO CRUD (read.py, update.py, delete.py)
│   │   ├── collections/    # Collection operations
│   │   ├── info/           # Metadata endpoints
│   │   └── storage/        # Storage-level operations
│   ├── services/           # Business logic (ApiRouter, StorageManager, etc.)
│   └── shared/             # Common code (models, exceptions, base classes)
└── tests/                  # Mirrors src/ structure exactly
    ├── conftest.py         # Shared fixtures, MockServiceProvider
    └── fixtures/           # Test utilities (boto mocks)

smithy/                     # API definitions → generates OpenAPI for CDK
└── models/
    ├── main.smithy         # Service definitions
    ├── storage/            # Storage API models
    └── token/              # Token API models
```

## Architecture Patterns

### ServiceProvider (Dependency Injection)
- Located in `lambda/src/environment/service_provider.py`
- Uses `@cached_property` for lazy initialization of all dependencies
- Provides: `session`, `dynamodb_table`, `storage_manager`, `user_manager`, `storage_api_router`
- Override `session` property in tests via `MockServiceProvider`

### Route Pattern
Each route is a class inheriting from `BaseRoute` with two required methods:

```python
class ExampleRoute(BaseRoute):
    def __init__(self, storage_manager: StorageManager):
        self.storage_manager = storage_manager

    def bind(self, api: API):
        @api.get("/path/{param}")
        @api.pass_event
        def handle_with_event(event: dict) -> Response:
            return self.handle(event)

    def handle(self, event: dict) -> Response:
        # Implementation with try/except for custom exceptions
        # Return aws_lambda_proxy.Response with appropriate StatusCode
```

### Route File Organization
- One route class per file: `routes/<resource>/<operation>.py`
- Examples: `routes/bso/read.py`, `routes/collections/create.py`
- Register routes in `ServiceProvider.storage_api_router`

### Exception Handling
Routes catch and map custom exceptions to HTTP status codes:
- `ValidationException` → 400 Bad Request
- `CollectionNotFoundException` / `StorageObjectNotFoundException` → 404 Not Found
- `ConflictException` → 409 Conflict
- `PreconditionFailedException` → 412 Precondition Failed
- Generic `Exception` → 500 Internal Server Error (log error)

## Testing Conventions

### Test Structure
- Tests mirror source: `tests/routes/bso/test_read.py` for `src/routes/bso/read.py`
- Use `MockServiceProvider` from `conftest.py` for integration tests
- Use `mock_storage_manager` fixture for unit testing routes

### Key Fixtures (conftest.py)
- `mock_service_provider` - MockServiceProvider with stubbed boto session
- `mock_storage_manager` - MagicMock with pre-configured return values
- `sample_lambda_event`, `sample_lambda_context` - Lambda invocation mocks
- `sample_bso`, `sample_collection`, `sample_batch_result` - Domain objects

### Coverage Requirement
- 100% test coverage required
- Use `# pragma: nocover` sparingly for unreachable code paths

## Code Style

### Python
- Black formatter (line-length 100)
- isort for imports
- Type hints on function signatures
- Logger from `aws_lambda_powertools`
- Dataclasses with `dataclasses-json` for models

### TypeScript
- ESLint + Prettier
- Strict mode enabled
