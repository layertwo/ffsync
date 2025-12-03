# SyncStorage Lambda API

A modular Lambda function implementation for the SyncStorage API using the `aws-lambda-proxy` package for API Gateway integration.

## Architecture

This implementation uses an `ApiRouter` class that registers route classes to handle API Gateway requests. Each route is implemented as a separate class following the CRUD naming convention and organized by resource type.

## API Endpoints

Based on the Smithy model, the following endpoints are implemented:

### Storage Operations
- `DELETE /storage` - Delete all storage data for the authenticated user

### Info/Metadata Operations
- `GET /info/collections` - Get metadata for all collections
- `GET /info/collection_counts` - Get object counts for all collections
- `GET /info/collection_usage` - Get storage usage for all collections
- `GET /info/quota` - Get storage quota information

### Collection Operations
- `GET /storage` - List all collections with their metadata
- `POST /storage/{collectionName}` - Create a new collection
- `GET /storage/{collectionName}` - Get collection metadata
- `PUT /storage/{collectionName}` - Update collection with batch objects
- `DELETE /storage/{collectionName}` - Delete an entire collection

### Basic Storage Object Operations
- `GET /storage/{collectionName}/{objectId}` - Get a specific storage object
- `PUT /storage/{collectionName}/{objectId}` - Update a storage object
- `DELETE /storage/{collectionName}/{objectId}` - Delete a specific storage object

## Key Features

### 1. Modular Route System
Each route is implemented as a separate class that extends `BaseRoute`. Routes are automatically registered with the `ApiRouter` using a decorator on each route.

### 2. Error Handling
Comprehensive error handling with proper HTTP status codes:
- `ValidationException` (400) - Invalid request parameters
- `AuthenticationException` (401) - Authentication required
- `ConflictException` (409) - Resource conflict
- `PreconditionFailedException` (412) - Precondition failed
- `ContentTooLargeException` (413) - Request entity too large
- `CollectionNotFoundException` (404) - Collection not found
- `QuotaExceededException` (507) - Storage quota exceeded

### 3. Authentication Integration
AWS SigV4 authentication validation (placeholder implementation provided).

### 4. CORS Support
All routes automatically include CORS headers for cross-origin requests.

## Usage

### Installation
```bash
pip install -r requirements.txt
```

### Deployment
The `lambda_handler` function in `main.py` serves as the AWS Lambda entry point. Deploy this function to AWS Lambda and configure API Gateway to proxy all requests to it.

### Adding New Routes
1. Create a new route class extending `BaseRoute`
2. Implement the required `method`, `path`, and `handle` properties/methods
3. Add the class to `ServiceProvider.api_router` routes 

Example:
```python
from shared.base_route import BaseRoute

class NewRoute(BaseRoute):
    method = 'GET'
    path = '/new-endpoint'
    
    def handle(self, event, context):
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": '{"message": "Hello from new route"}'
        }
```

## TODO Items

All route implementations currently contain TODO comments for:
- Authentication validation integration
- Proper timestamp generation
- Request payload parsing and validation
- Response header management (X-Last-Modified, X-If-Unmodified-Since)
- Batch operation logic
- Quota enforcement

## Testing

Each route class can be unit tested independently by instantiating the class and calling the `handle` method with mock API Gateway events.
