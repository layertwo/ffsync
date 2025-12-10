# Token Server Design Document

## Overview

The Token Server is a serverless AWS Lambda function that implements the Firefox Sync authentication protocol. It serves as the authentication gateway for Firefox Sync clients, validating user credentials via OIDC providers and issuing time-limited bearer tokens with HAWK credentials for accessing the Storage API.

The Token Server acts as a bridge between modern OIDC authentication and the Firefox Sync protocol, enabling users to authenticate with their chosen identity provider (Authentik, Authelia, Pocket ID, etc.) while maintaining compatibility with the Firefox Sync client expectations.

**Key Design Principles:**
- **Serverless-first**: Leverage AWS Lambda for automatic scaling and cost efficiency
- **Stateless authentication**: Use OIDC token validation without session management
- **Secure by default**: Cryptographic token generation and validation
- **Protocol compliance**: Adhere to Mozilla Token Server specification
- **Extensible**: Support multiple OIDC providers through configuration

## Architecture

### High-Level Architecture

```
┌─────────────────┐
│ Firefox Sync    │
│ Client          │
└────────┬────────┘
         │ POST /1.0/sync/1.5
         │ Authorization: Bearer <OIDC_TOKEN>
         ▼
┌─────────────────────────────────────────┐
│ API Gateway                             │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ Token Server Lambda                     │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │ Request Handler                  │  │
│  │ - Parse Authorization header     │  │
│  │ - Route to token endpoint        │  │
│  └──────────┬───────────────────────┘  │
│             │                           │
│  ┌──────────▼───────────────────────┐  │
│  │ OIDC Validator                   │  │
│  │ - Fetch JWKS from provider       │  │
│  │ - Verify token signature         │  │
│  │ - Validate claims (iss, aud, exp)│  │
│  │ - Extract user identifier        │  │
│  └──────────┬───────────────────────┘  │
│             │                           │
│  ┌──────────▼───────────────────────┐  │
│  │ User Manager                     │  │
│  │ - Get/create user record         │  │
│  │ - Assign node if needed          │  │
│  │ - Validate generation number     │  │
│  └──────────┬───────────────────────┘  │
│             │                           │
│  ┌──────────▼───────────────────────┐  │
│  │ Token Generator                  │  │
│  │ - Generate HAWK credentials      │  │
│  │ - Create bearer token            │  │
│  │ - Build response payload         │  │
│  └──────────────────────────────────┘  │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ DynamoDB                                │
│ - User records                          │
│ - Node assignments                      │
│ - Generation numbers                    │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ OIDC Provider                           │
│ - JWKS endpoint                         │
│ - OpenID configuration                  │
└─────────────────────────────────────────┘
```

### Component Interaction Flow

1. **Request Reception**: API Gateway receives POST request with OIDC token in Authorization header
2. **Token Validation**: Lambda validates OIDC token with provider's JWKS endpoint
3. **User Lookup**: Lambda queries DynamoDB for existing user record or creates new one
4. **Token Generation**: Generate HAWK credentials and construct api_endpoint dynamically
5. **Response**: Return JSON with token, endpoint, duration, and user ID

## Components and Interfaces

### 1. Request Handler

**Responsibility**: Parse incoming requests, validate HTTP parameters, route to appropriate handlers

**Interface**:
```python
class TokenRequestHandler:
    def handle_request(self, event: dict, context: LambdaContext) -> dict:
        """
        Main entry point for Lambda invocations
        
        Args:
            event: API Gateway proxy event
            context: Lambda context
            
        Returns:
            API Gateway proxy response
        """
        pass
    
    def validate_request(self, event: dict) -> tuple[bool, Optional[str]]:
        """
        Validate request structure and headers
        
        Returns:
            (is_valid, error_message)
        """
        pass
```

**Key Validations**:
- HTTP method is POST
- Path matches `/1.0/sync/1.5`
- Authorization header is present
- Content-Type is appropriate
- X-Client-State header format (if present): hexadecimal string, max 32 characters

**X-Client-State Handling**:
- Extract X-Client-State header from request (default to empty string if absent)
- Validate format: must be hexadecimal characters only, max 32 characters
- Pass to UserManager for client state tracking and generation increment logic

**Response Headers**:
- All responses (success and error) include `X-Timestamp` header with current Unix epoch seconds

**CORS Handling**:
- API Gateway handles all CORS configuration and OPTIONS requests
- Lambda does not need to handle OPTIONS requests or add CORS headers
- API Gateway automatically adds CORS headers to all responses (including errors)
- CORS configuration includes: `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`

**Design Decision**: Use API Gateway proxy integration to receive full HTTP context, enabling comprehensive validation and error handling at the Lambda level. Delegate CORS handling entirely to API Gateway configuration rather than implementing it in Lambda code.

**Rationale**: API Gateway's built-in CORS support is simpler, more cost-effective (OPTIONS requests don't invoke Lambda), and ensures consistent CORS headers across all responses including errors. This reduces Lambda code complexity and follows AWS best practices for serverless applications.

### 2. OIDC Validator

**Responsibility**: Validate OIDC tokens against configured provider

**Interface**:
```python
class OIDCValidator:
    def __init__(self, provider_url: str, client_id: str):
        """
        Initialize with OIDC provider configuration
        
        Args:
            provider_url: Base URL of OIDC provider
            client_id: Expected audience claim value
        """
        pass
    
    def validate_token(self, token: str) -> OIDCTokenClaims:
        """
        Validate OIDC token and extract claims
        
        Args:
            token: Raw OIDC token string
            
        Returns:
            Validated token claims
            
        Raises:
            InvalidTokenError: If token is invalid
        """
        pass
    
    def discover_provider_config(self) -> OIDCProviderConfig:
        """
        Fetch OIDC provider configuration from .well-known endpoint
        
        Returns:
            Provider configuration including JWKS URI
        """
        pass
```

**Token Validation Steps**:
1. Fetch OIDC provider configuration (cached with TTL)
2. Retrieve JWKS from provider
3. Verify token signature using public key
4. Validate issuer matches configured provider
5. Validate audience matches configured client ID
6. Verify token has not expired
7. Extract user identifier from `sub` claim

**Design Decision**: Use PyJWT library for token validation with JWKS support. Cache provider configuration and JWKS for 1 hour to reduce external API calls.

**Rationale**: PyJWT is well-maintained, supports RS256 algorithm commonly used by OIDC providers, and handles JWKS fetching. Caching reduces latency and external dependencies while maintaining security (1-hour TTL allows for key rotation).

### 3. User Manager

**Responsibility**: Manage user records in DynamoDB, handle generation numbers for token invalidation, track client state for key rotation

**Interface**:
```python
@dataclass
class UserRecord:
    user_id: str
    generation: int
    client_state: str
    created_at: float
    updated_at: float

class UserManager:
    def __init__(self, dynamodb_table):
        """
        Initialize with DynamoDB table resource
        
        Args:
            dynamodb_table: boto3 DynamoDB table resource
        """
        pass
    
    def get_or_create_user(self, user_id: str, client_state: str = "") -> UserRecord:
        """
        Get existing user or create new record.
        If client_state differs from stored value, increment generation.
        
        Args:
            user_id: Unique user identifier from OIDC token
            client_state: X-Client-State header value (hex string, max 32 chars)
            
        Returns:
            User record with current generation number
        """
        pass
    
    def increment_generation(self, user_id: str) -> int:
        """
        Increment user's generation number (invalidates old tokens)
        
        Args:
            user_id: User identifier
            
        Returns:
            New generation number
        """
        pass
    
    def validate_generation(self, user_id: str, generation: int) -> bool:
        """
        Verify generation number matches current value
        
        Args:
            user_id: User identifier
            generation: Generation number to validate
            
        Returns:
            True if generation is current
        """
        pass
    
    def update_client_state(self, user_id: str, client_state: str) -> bool:
        """
        Update client state and increment generation if changed
        
        Args:
            user_id: User identifier
            client_state: New X-Client-State value
            
        Returns:
            True if generation was incremented (state changed)
        """
        pass
```

**DynamoDB Schema**:
```
Table: TokenServerUsers
Partition Key: user_id (String)

Attributes:
- user_id: String (PK)
- generation: Number (default: 0)
- client_state: String (default: "")
- created_at: Number (timestamp)
- updated_at: Number (timestamp)
```

**Node Assignment Strategy**:
- Node assignment is computed dynamically, not stored
- Format: `https://{base_url}/1.5/{user_id}`
- Base URL from environment variable `STORAGE_BASE_URL`
- Constructed on-demand for each token response

**Design Decision**: Remove node assignment persistence from DynamoDB. Since we're serverless with a single storage backend, node assignment can be computed dynamically from the base URL and user ID.

**Rationale**: Simplifies data model and reduces storage requirements. In a serverless architecture, all users share the same storage infrastructure, so persisting node assignment adds unnecessary complexity. Dynamic construction ensures consistency without database overhead.

### 4. Token Generator

**Responsibility**: Generate HAWK credentials and construct token response

**Interface**:
```python
@dataclass
class TokenResponse:
    id: str  # HAWK identifier
    key: str  # HAWK shared secret
    api_endpoint: str  # Storage API URL
    uid: int  # User ID (hashed)
    duration: int  # Token validity in seconds
    hashalg: str  # Hash algorithm for HAWK

class TokenGenerator:
    def generate_token(
        self, 
        user_id: str, 
        generation: int, 
        storage_base_url: str
    ) -> TokenResponse:
        """
        Generate HAWK credentials and token response
        
        Args:
            user_id: User identifier
            generation: Current generation number
            storage_base_url: Base URL for storage endpoint
            
        Returns:
            Complete token response with dynamically constructed api_endpoint
        """
        pass
    
    def generate_hawk_id(self, user_id: str, generation: int) -> str:
        """
        Generate HAWK identifier (URL-safe base64)
        
        Format: {user_id}:{generation}:{expiry}
        """
        pass
    
    def generate_hawk_key(self) -> str:
        """
        Generate cryptographically random HAWK shared secret
        
        Returns:
            64-character hex string (32 bytes)
        """
        pass
```

**HAWK Credential Generation**:
- **HAWK ID**: Base64-encoded string containing `{user_id}:{generation}:{expiry_timestamp}`
- **HAWK Key**: 32 bytes of cryptographically random data, hex-encoded
- **Duration**: 300 seconds (5 minutes)
- **Hash Algorithm**: SHA-256

**Design Decision**: Embed generation number and expiry in HAWK ID to enable stateless validation by Storage API. Use secrets.token_bytes() for cryptographic randomness.

**Rationale**: Stateless token design allows Storage API to validate tokens without querying Token Server. Embedding metadata in HAWK ID enables validation of generation number and expiry.

### 5. Error Handler

**Responsibility**: Format error responses according to Firefox Sync protocol

**Interface**:
```python
@dataclass
class ErrorDetail:
    location: str
    name: str
    description: str

class ErrorResponse:
    def format_error(
        self, 
        status_code: int, 
        error_type: str, 
        errors: List[ErrorDetail]
    ) -> dict:
        """
        Format error response for API Gateway
        
        Args:
            status_code: HTTP status code
            error_type: Error type identifier
            errors: List of error details
            
        Returns:
            API Gateway proxy response
        """
        pass
```

**Error Response Format**:
```json
{
  "status": "error-type",
  "errors": [
    {
      "location": "header",
      "name": "Authorization",
      "description": "Missing or invalid authorization header"
    }
  ]
}
```

**Standard Error Types**:
- `invalid-credentials`: Authentication failed (401)
- `invalid-request`: Malformed request (400)
- `not-found`: Endpoint not found (404)
- `method-not-allowed`: Wrong HTTP method (405)
- `unsupported-media-type`: Wrong Content-Type (415)
- `service-unavailable`: OIDC provider unreachable (503)

## Data Models

### User Record
```python
@dataclass
class UserRecord:
    user_id: str          # Unique identifier from OIDC sub claim
    generation: int       # Monotonic counter for token invalidation
    client_state: str     # X-Client-State header value (hex string, max 32 chars)
    created_at: float     # Unix timestamp
    updated_at: float     # Unix timestamp
```

### OIDC Token Claims
```python
@dataclass
class OIDCTokenClaims:
    sub: str              # Subject (user identifier)
    iss: str              # Issuer URL
    aud: str              # Audience (client ID)
    exp: int              # Expiry timestamp
    iat: int              # Issued at timestamp
    email: Optional[str]  # User email (optional)
```

### Token Response
```python
@dataclass
class TokenResponse:
    id: str               # HAWK identifier
    key: str              # HAWK shared secret (hex)
    api_endpoint: str     # Full storage API URL
    uid: int              # Numeric user ID (hash of user_id)
    duration: int         # Token validity (300 seconds)
    hashalg: str          # "sha256"
```

### OIDC Provider Configuration
```python
@dataclass
class OIDCProviderConfig:
    issuer: str
    jwks_uri: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


### Property Reflection

After analyzing all acceptance criteria, I've identified several areas where properties can be consolidated:

**Redundancies identified:**
- Properties 1.1 and 2.5 both verify response structure - can be combined into a comprehensive response validation property
- Properties 4.1 and 4.2 both verify HAWK credential fields - can be combined with 1.1 into response structure validation
- Property 7.4 duplicates 3.4 (both verify new users have generation 0)
- Properties 6.2 and 6.3 can be combined into a single error response structure property
- Requirements 2.1-2.4 all relate to node assignment, which is now computed dynamically rather than persisted
- Properties 14.1 and 14.2 (X-Timestamp on success/error) can be combined into a single property

**Properties to combine:**
- Response structure validation (1.1, 2.5, 4.1, 4.2) → Single property verifying all required fields
- Node assignment (2.1, 2.2, 2.3, 2.4) → Single property verifying URL format (no persistence needed)
- Error response structure (6.2, 6.3) → Single property verifying error format
- X-Timestamp headers (14.1, 14.2) → Single property verifying header presence on all responses

**Simplification: Node Assignment**
Since we're using a serverless architecture with a single storage backend, node assignment is computed dynamically from `{base_url}/1.5/{user_id}` rather than persisted in DynamoDB. This eliminates the need for:
- Storing node_assignment field in user records
- Testing node assignment persistence
- Testing node assignment idempotence (it's inherently idempotent when computed)

**Simplification: CORS Handling**
API Gateway handles all CORS configuration and OPTIONS requests automatically. This eliminates the need for:
- Lambda handling OPTIONS requests (Requirement 8.1)
- Lambda adding CORS headers to responses (Requirements 8.2, 8.3, 8.4)
- Testing CORS header presence in Lambda responses

CORS is configured at the API Gateway level and applies consistently to all responses, including errors. This reduces Lambda complexity and follows AWS best practices.

**New Requirements Analysis (13, 14):**

13.1 X-Client-State storage
  Thoughts: This is a rule about all requests with the header. We can generate random client states and verify they are stored.
  Testable: yes - property

13.2 X-Client-State change triggers generation increment
  Thoughts: This is a rule about state changes. We can create a user, then send a different client state and verify generation increments.
  Testable: yes - property

13.3 X-Client-State default value
  Thoughts: This is about requests without the header. We can verify empty string is used.
  Testable: yes - property

13.4 X-Client-State format validation
  Thoughts: This is about validating hex format. We can generate valid/invalid hex strings and verify behavior.
  Testable: yes - property

13.5 Invalid X-Client-State rejection
  Thoughts: This is about error handling for invalid format. We can generate invalid formats and verify 400 response.
  Testable: yes - property

14.1 X-Timestamp on success
  Thoughts: This is about response headers. We can verify all success responses include the header.
  Testable: yes - property

14.2 X-Timestamp on error
  Thoughts: This is about response headers. We can verify all error responses include the header.
  Testable: yes - property (can combine with 14.1)

14.3 X-Timestamp format
  Thoughts: This is about header format. We can verify the value is an integer.
  Testable: yes - property

This consolidation reduces redundancy and complexity while maintaining comprehensive coverage of all requirements.

### Correctness Properties

**Property 1: Complete token response structure**
*For any* valid OIDC token, the Token Server response SHALL contain all required fields: `id`, `key`, `api_endpoint`, `uid`, `duration`, and `hashalg`.
**Validates: Requirements 1.1, 2.5, 4.1, 4.2**

**Property 2: OIDC token validation**
*For any* request with an OIDC token, the Token Server SHALL validate the token with the configured OIDC provider before issuing credentials.
**Validates: Requirements 1.2**

**Property 3: Invalid credentials rejection**
*For any* invalid OIDC token, the Token Server SHALL return a 401 status code with an error message.
**Validates: Requirements 1.3**

**Property 4: Malformed header rejection**
*For any* malformed Authorization header, the Token Server SHALL return a 400 status code with a validation error.
**Validates: Requirements 1.4**

**Property 5: Token duration consistency**
*For any* issued bearer token, the `duration` field SHALL equal 300 seconds.
**Validates: Requirements 1.5**

**Property 6: Node URL format**
*For any* token response, the `api_endpoint` SHALL match the format `https://{base_url}/1.5/{user_id}`.
**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

**Property 7: Generation-based token invalidation**
*For any* user, when the generation number is incremented, all previously issued tokens SHALL be rejected with a 401 status code.
**Validates: Requirements 3.1, 3.3**

**Property 8: Generation number validation**
*For any* bearer token validation, the Token Server SHALL verify the token's generation number matches the current user generation.
**Validates: Requirements 3.2**

**Property 9: Default generation number**
*For any* newly created user record, the generation number SHALL be 0.
**Validates: Requirements 3.4, 7.4**

**Property 10: Generation number monotonicity**
*For any* generation number update, the new value SHALL be greater than the previous value.
**Validates: Requirements 3.5**

**Property 11: HAWK ID format**
*For any* generated HAWK credentials, the `id` SHALL be a valid URL-safe base64-encoded string.
**Validates: Requirements 4.3**

**Property 12: HAWK key format and randomness**
*For any* generated HAWK credentials, the `key` SHALL be a 64-character hexadecimal string (32 bytes), and multiple generations SHALL produce unique keys.
**Validates: Requirements 4.4**

**Property 13: Invalid path rejection**
*For any* request to a path other than `/1.0/sync/1.5`, the Token Server SHALL return a 404 status code.
**Validates: Requirements 5.2**

**Property 14: Unsupported method rejection**
*For any* request with an HTTP method other than POST or OPTIONS, the Token Server SHALL return a 405 status code.
**Validates: Requirements 5.3**

**Property 15: Invalid content type rejection**
*For any* request with an unsupported Content-Type, the Token Server SHALL return a 415 status code.
**Validates: Requirements 5.4**

**Property 16: Error message presence**
*For any* validation error, the response SHALL include a descriptive error message.
**Validates: Requirements 5.5**

**Property 17: Error response JSON validity**
*For any* error response, the response body SHALL be valid JSON.
**Validates: Requirements 6.1**

**Property 18: Error response structure**
*For any* error response, the JSON SHALL contain a `status` field with the error type and an `errors` array with error details.
**Validates: Requirements 6.2, 6.3**

**Property 19: 401 error status value**
*For any* 401 error response, the `status` field SHALL contain "invalid-credentials".
**Validates: Requirements 6.4**

**Property 20: Validation error structure**
*For any* validation error, each object in the `errors` array SHALL contain `location`, `name`, and `description` fields.
**Validates: Requirements 6.5**

**Property 21: User record DynamoDB structure**
*For any* created user record, the record SHALL be stored in DynamoDB with `user_id` as the partition key.
**Validates: Requirements 7.1**

**Property 22: User record required fields**
*For any* stored user record, the record SHALL include `user_id`, `generation`, `created_at`, and `updated_at` fields.
**Validates: Requirements 7.2**

**Property 23: Updated timestamp modification**
*For any* user record update, the `updated_at` timestamp SHALL be greater than the previous value.
**Validates: Requirements 7.5**

**Property 24: OIDC signature verification**
*For any* OIDC token validation, the Token Server SHALL verify the token signature using the provider's JWKS endpoint.
**Validates: Requirements 9.3**

**Property 25: OIDC issuer validation**
*For any* OIDC token, the Token Server SHALL reject tokens where the issuer does not match the configured OIDC provider.
**Validates: Requirements 9.4**

**Property 26: OIDC audience validation**
*For any* OIDC token, the Token Server SHALL reject tokens where the audience does not match the expected client ID.
**Validates: Requirements 9.5**

**Property 27: OIDC provider unreachable error**
*For any* request when the OIDC provider is unreachable, the Token Server SHALL return a 503 status code with a service unavailable error.
**Validates: Requirements 10.5**

**Property 28: User identifier extraction**
*For any* OIDC token, the Token Server SHALL extract the user identifier from the `sub` claim.
**Validates: Requirements 11.1**

**Property 29: Token expiry validation**
*For any* OIDC token validation, the Token Server SHALL reject expired tokens (based on `exp` claim) with a 401 status code.
**Validates: Requirements 11.2, 11.3**

**Property 30: Missing user identifier rejection**
*For any* OIDC token without a `sub` claim, the Token Server SHALL return a 401 status code.
**Validates: Requirements 11.4**

**Property 31: User identifier consistency**
*For any* token request, the same user identifier SHALL be used for token generation and database operations.
**Validates: Requirements 11.5**

**Property 32: Successful authentication logging**
*For any* successful token issuance, the Token Server SHALL log the user identifier and timestamp.
**Validates: Requirements 12.1**

**Property 33: Failed authentication logging**
*For any* authentication failure, the Token Server SHALL log the failure reason and timestamp.
**Validates: Requirements 12.2**

**Property 34: Validation error logging**
*For any* validation error, the Token Server SHALL log the error details.
**Validates: Requirements 12.3**

**Property 35: Structured logging format**
*For any* log entry, the Token Server SHALL use structured logging with JSON format.
**Validates: Requirements 12.4**

**Property 36: Sensitive data exclusion from logs**
*For any* log entry, the Token Server SHALL NOT include bearer tokens, HAWK keys, or other sensitive credentials.
**Validates: Requirements 12.5**

**Property 37: X-Client-State storage**
*For any* request with an X-Client-State header, the Token Server SHALL store the client state value with the user record.
**Validates: Requirements 13.1**

**Property 38: X-Client-State change triggers generation increment**
*For any* request where X-Client-State differs from the previously stored value, the Token Server SHALL increment the user's generation number.
**Validates: Requirements 13.2, 3.6**

**Property 39: X-Client-State default value**
*For any* request without an X-Client-State header, the Token Server SHALL use an empty string as the default value.
**Validates: Requirements 13.3**

**Property 40: X-Client-State format validation**
*For any* X-Client-State header value, the Token Server SHALL validate it is a hexadecimal string of up to 32 characters.
**Validates: Requirements 13.4**

**Property 41: Invalid X-Client-State rejection**
*For any* request with an invalid X-Client-State format, the Token Server SHALL return a 400 status code with a validation error.
**Validates: Requirements 13.5**

**Property 42: X-Timestamp header on success**
*For any* successful response, the Token Server SHALL include an X-Timestamp header with the current server time in seconds since epoch.
**Validates: Requirements 14.1**

**Property 43: X-Timestamp header on error**
*For any* error response, the Token Server SHALL include an X-Timestamp header with the current server time in seconds since epoch.
**Validates: Requirements 14.2**

**Property 44: X-Timestamp format**
*For any* X-Timestamp header value, the value SHALL be an integer representing Unix epoch seconds.
**Validates: Requirements 14.3**

## Error Handling

### Error Categories

**1. Authentication Errors (401)**
- Invalid OIDC token signature
- Expired OIDC token
- Missing or malformed Authorization header
- Token with wrong issuer or audience
- Outdated generation number
- Missing `sub` claim in token

**2. Validation Errors (400)**
- Malformed request body
- Invalid JSON payload
- Missing required fields
- Malformed Authorization header format

**3. Not Found Errors (404)**
- Invalid endpoint path
- Unsupported API version

**4. Method Not Allowed (405)**
- Using GET, PUT, DELETE, etc. on token endpoint

**5. Unsupported Media Type (415)**
- Wrong Content-Type header

**6. Service Unavailable (503)**
- OIDC provider unreachable
- DynamoDB connection failure
- Temporary service degradation

### Error Response Format

All errors follow the Firefox Sync protocol format:

```json
{
  "status": "error-type",
  "errors": [
    {
      "location": "header|body|query",
      "name": "field-name",
      "description": "Human-readable error description"
    }
  ]
}
```

### Error Handling Strategy

**Design Decision**: Implement centralized error handling middleware that catches exceptions and formats them according to the protocol.

**Rationale**: Centralized error handling ensures consistent error responses across all endpoints and simplifies error management. It also enables comprehensive logging of all errors for debugging and monitoring.

**Implementation Approach**:
1. Define custom exception classes for each error category
2. Implement error handler that catches exceptions and formats responses
3. Include request context in error logs (request ID, user ID if available)
4. Sanitize error messages to avoid leaking sensitive information

### Retry Strategy

**For OIDC Provider Calls**:
- Retry up to 3 times with exponential backoff (100ms, 200ms, 400ms)
- Return 503 if all retries fail
- Cache successful JWKS responses for 1 hour

**For DynamoDB Operations**:
- Use boto3 default retry strategy (exponential backoff)
- Return 503 for persistent failures
- Log all retry attempts for monitoring

## Testing Strategy

### Unit Testing

**Framework**: pytest with pytest-mock for mocking external dependencies

**Coverage Goals**:
- 90%+ code coverage for all components
- 100% coverage for critical paths (token generation, validation)

**Key Unit Tests**:
1. **Request Handler Tests**
   - Valid POST request handling
   - Invalid HTTP method rejection
   - Missing Authorization header handling
   - Malformed request handling

2. **OIDC Validator Tests**
   - Valid token validation
   - Expired token rejection
   - Invalid signature rejection
   - Wrong issuer/audience rejection
   - JWKS fetching and caching

3. **User Manager Tests**
   - New user creation with node assignment
   - Existing user retrieval
   - Generation number increment
   - Node assignment persistence

4. **Token Generator Tests**
   - HAWK ID generation and format
   - HAWK key randomness and format
   - Token response structure
   - Duration field value

5. **Error Handler Tests**
   - Error response formatting
   - Status code mapping
   - Error detail structure

### Property-Based Testing

**Framework**: Hypothesis (Python property-based testing library)

**Configuration**: Each property-based test will run a minimum of 100 iterations to ensure comprehensive coverage of the input space.

**Test Tagging**: Each property-based test MUST be tagged with a comment explicitly referencing the correctness property from the design document using this format: `# Feature: token-server, Property {number}: {property_text}`

**Key Property Tests**:

1. **Response Structure Properties**
   - Property 1: All valid tokens produce complete responses
   - Property 5: Duration is always 300 seconds
   - Property 8: Node URLs always match format

2. **Validation Properties**
   - Property 3: All invalid tokens return 401
   - Property 4: All malformed headers return 400
   - Property 29: All wrong issuers are rejected
   - Property 30: All wrong audiences are rejected

3. **Generation Number Properties**
   - Property 10: Old tokens rejected after generation increment
   - Property 13: Generation numbers always increase
   - Property 12: New users always start at generation 0

4. **HAWK Credential Properties**
   - Property 14: HAWK IDs are always valid base64
   - Property 15: HAWK keys are always unique and properly formatted

5. **Error Response Properties**
   - Property 20: All errors produce valid JSON
   - Property 21: All errors have required structure
   - Property 27: All responses include CORS headers

6. **Idempotence Properties**
   - Property 7: Multiple requests return same node assignment
   - Property 9: Node assignment unchanged by generation increment

7. **Logging Properties**
   - Property 39: All logs are valid JSON
   - Property 40: No sensitive data in logs

### Integration Testing

**Scope**: Test complete request flow from API Gateway event to response

**Key Integration Tests**:
1. End-to-end token issuance with real OIDC token validation (using test provider)
2. Token invalidation flow (issue token, increment generation, verify rejection)
3. First-time user flow (no existing record → node assignment → token issuance)
4. Returning user flow (existing record → same node → token issuance)
5. Error scenarios with real AWS services (DynamoDB, OIDC provider)

**Test Environment**:
- Use LocalStack for DynamoDB testing
- Mock OIDC provider with test JWKS endpoint
- Use pytest fixtures for test data setup

### Testing Best Practices

1. **Isolation**: Each test should be independent and not rely on shared state
2. **Mocking**: Mock external dependencies (OIDC provider, DynamoDB) in unit tests
3. **Test Data**: Use factories or fixtures to generate test data consistently
4. **Assertions**: Use specific assertions that clearly indicate what failed
5. **Coverage**: Aim for high coverage but focus on critical paths first
6. **Performance**: Keep unit tests fast (<100ms each) for rapid feedback

### CORS Testing

**Note**: CORS is handled entirely by API Gateway configuration, not Lambda code. Therefore:
- Lambda unit tests do not need to verify CORS headers
- Lambda integration tests do not need to test OPTIONS request handling
- CORS functionality should be verified through infrastructure tests or manual testing of the deployed API Gateway
- Requirements 8.1-8.4 are satisfied through API Gateway configuration, not Lambda implementation

## Security Considerations

### Token Security

**HAWK Key Generation**:
- Use `secrets.token_bytes(32)` for cryptographically secure random generation
- Never reuse HAWK keys across different tokens
- Encode as hexadecimal for safe transmission

**Token Expiry**:
- Short-lived tokens (300 seconds) limit exposure window
- No token refresh mechanism (clients must re-authenticate)
- Generation number enables immediate invalidation

### OIDC Token Validation

**Signature Verification**:
- Always verify token signature using JWKS from provider
- Reject tokens with invalid or missing signatures
- Cache JWKS with reasonable TTL (1 hour) to balance security and performance

**Claim Validation**:
- Verify issuer matches configured provider (prevents token substitution)
- Verify audience matches expected client ID (prevents token misuse)
- Verify expiry timestamp (prevents replay attacks)
- Extract user identifier from `sub` claim only after validation

### Data Protection

**Sensitive Data Handling**:
- Never log bearer tokens, HAWK keys, or OIDC tokens
- Use structured logging to control what gets logged
- Sanitize error messages to avoid leaking sensitive information

**DynamoDB Security**:
- Use IAM roles for Lambda-to-DynamoDB authentication
- Enable encryption at rest for DynamoDB table
- Use VPC endpoints for private communication (optional)

### Input Validation

**Request Validation**:
- Validate all input parameters before processing
- Reject requests with unexpected fields
- Enforce strict type checking
- Limit request size to prevent DoS

**Authorization Header Parsing**:
- Validate header format before extraction
- Handle malformed headers gracefully
- Reject headers with unexpected schemes

## Performance Considerations

### Latency Optimization

**Target Latency**: < 200ms for token issuance (p95)

**Optimization Strategies**:
1. **JWKS Caching**: Cache OIDC provider JWKS for 1 hour to avoid repeated fetches
2. **Provider Config Caching**: Cache OpenID configuration for 1 hour
3. **DynamoDB Optimization**: Use consistent reads only when necessary (default to eventually consistent)
4. **Connection Pooling**: Reuse HTTP connections for OIDC provider calls
5. **Lambda Warm-up**: Keep Lambda instances warm with periodic health checks

### Scalability

**Concurrency**:
- Lambda auto-scales to handle concurrent requests
- DynamoDB on-demand pricing scales automatically
- No shared state between requests enables horizontal scaling

**Rate Limiting**:
- Implement at API Gateway level (not in Lambda)
- Suggested limit: 100 requests per minute per IP
- Return 429 status code when limit exceeded

### Cost Optimization

**Lambda**:
- Use ARM64 architecture for better price/performance
- Optimize memory allocation (recommend 512MB)
- Minimize cold start time with small deployment package

**DynamoDB**:
- Use on-demand pricing for unpredictable traffic
- Consider provisioned capacity for steady-state traffic
- Enable TTL for automatic cleanup of old records (if needed)

**OIDC Provider Calls**:
- Cache responses to minimize external API calls
- Use conditional requests (If-Modified-Since) when possible

## Deployment Considerations

### Environment Variables

**Required**:
- `STAGE`: Deployment stage (e.g., `beta`, `prod`)
- `BASE_DOMAIN`: Stage-qualified base domain (e.g., `beta.ffsync.layertwo.dev`)
- `OIDC_SECRET_ARN`: ARN of Secrets Manager secret containing OIDC configuration
- `TOKEN_USERS_TABLE_NAME`: Name of DynamoDB table for user records

**Optional**:
- `LOG_LEVEL`: Logging level (default: INFO)
- `JWKS_CACHE_TTL`: JWKS cache TTL in seconds (default: 3600)
- `TOKEN_DURATION`: Token validity in seconds (default: 300)

### OIDC Secret Configuration

The OIDC configuration is stored in AWS Secrets Manager with the name `ffsync-oidc-config-{stage}`.

**Secret JSON Structure**:
```json
{
  "provider_url": "https://auth.example.com",
  "client_id": "your-client-id"
}
```

**Fields**:
- `provider_url`: Base URL of the OIDC provider (e.g., `https://auth.example.com`). The Token Server will discover the provider's configuration from `{provider_url}/.well-known/openid-configuration`.
- `client_id`: Expected audience (`aud`) claim value in OIDC tokens. Tokens with a different audience will be rejected.

**Example for Authentik**:
```json
{
  "provider_url": "https://authentik.example.com/application/o/firefox-sync",
  "client_id": "firefox-sync-client-id"
}
```

**Example for Authelia**:
```json
{
  "provider_url": "https://auth.example.com",
  "client_id": "firefox-sync"
}
```

### Infrastructure Requirements

**Lambda Configuration**:
- Runtime: Python 3.11 or later
- Memory: 512MB (recommended)
- Timeout: 30 seconds
- Architecture: ARM64 (recommended for cost)

**DynamoDB Table**:
- Partition Key: `user_id` (String)
- Billing Mode: On-demand (or provisioned based on traffic)
- Encryption: Enabled (AWS managed key)
- Point-in-time recovery: Enabled (recommended)

**API Gateway**:
- REST API or HTTP API
- CORS configuration:
  - Enable CORS at API Gateway level (not in Lambda)
  - Allow-Origin: Configure based on deployment (e.g., `*` for public access or specific origins)
  - Allow-Methods: `POST, OPTIONS`
  - Allow-Headers: `Authorization, Content-Type`
  - API Gateway automatically handles OPTIONS preflight requests
- Request validation enabled
- CloudWatch logging enabled

### Monitoring and Observability

**CloudWatch Metrics**:
- Lambda invocations, errors, duration
- DynamoDB read/write capacity usage
- API Gateway 4xx and 5xx errors
- Custom metrics: token issuance rate, validation failures

**CloudWatch Logs**:
- Structured JSON logs for all requests
- Log groups with retention policy (30 days recommended)
- Log insights queries for common debugging scenarios

**Alarms**:
- Lambda error rate > 5%
- Lambda duration > 1000ms (p95)
- DynamoDB throttling events
- OIDC provider connection failures

**Tracing**:
- AWS X-Ray integration for request tracing
- Trace OIDC provider calls and DynamoDB operations
- Identify performance bottlenecks

### Disaster Recovery

**Backup Strategy**:
- DynamoDB point-in-time recovery enabled
- Daily backups to S3 (optional)
- Cross-region replication for high availability (optional)

**Rollback Plan**:
- Use Lambda versioning and aliases
- Implement blue-green deployment
- Keep previous version available for quick rollback

## Future Enhancements

### Potential Improvements

1. **Multi-Region Support**
   - Deploy Token Server in multiple regions
   - Use Route53 for geographic routing
   - Replicate DynamoDB table across regions

2. **Advanced Caching**
   - Use ElastiCache for JWKS and provider config
   - Share cache across Lambda instances
   - Reduce OIDC provider load

3. **Token Refresh**
   - Implement refresh token mechanism
   - Extend token lifetime without re-authentication
   - Maintain security with refresh token rotation

4. **Rate Limiting**
   - Implement per-user rate limiting
   - Use DynamoDB for distributed rate limit tracking
   - Prevent abuse and DoS attacks

5. **Metrics Dashboard**
   - Build CloudWatch dashboard for key metrics
   - Visualize token issuance trends
   - Monitor authentication success rates

6. **Audit Logging**
   - Implement comprehensive audit trail
   - Log all authentication events to S3
   - Enable compliance and security investigations

## Appendix

### References

- [Mozilla Token Server Specification](https://github.com/mozilla-services/tokenserver)
- [HAWK Authentication Scheme](https://github.com/mozilla/hawk)
- [OpenID Connect Core Specification](https://openid.net/specs/openid-connect-core-1_0.html)
- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)

### Glossary Expansion

- **JWT (JSON Web Token)**: Compact, URL-safe token format used by OIDC providers
- **JWKS (JSON Web Key Set)**: Set of public keys used to verify JWT signatures
- **RS256**: RSA signature algorithm with SHA-256, commonly used for JWT signing
- **Base64URL**: URL-safe variant of Base64 encoding (no padding, uses - and _ instead of + and /)
- **HMAC**: Hash-based Message Authentication Code, used in HAWK authentication
- **Bearer Token**: Token type that grants access to resources simply by possessing it
- **Partition Key**: Primary key attribute in DynamoDB used for data distribution
- **Cold Start**: Initial invocation delay when Lambda creates new execution environment
- **Idempotence**: Property where multiple identical requests have the same effect as a single request
