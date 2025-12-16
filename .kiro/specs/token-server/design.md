# Token Server Design Document

## Overview

The Token Server is a serverless AWS Lambda function that implements the Mozilla Token Server API v1.0 specification. It serves as the authentication gateway for Firefox Sync clients, validating user credentials via OIDC providers and issuing time-limited bearer tokens with HAWK credentials for accessing the Storage API.

The Token Server acts as a bridge between modern OIDC authentication and the Firefox Sync protocol, enabling users to authenticate with their chosen identity provider (Authentik, Authelia, Pocket ID, etc.) while maintaining compatibility with the Firefox Sync client expectations.

**Key Design Principles:**
- **Serverless-first**: Leverage AWS Lambda for automatic scaling and cost efficiency
- **Stateless authentication**: Use OIDC token validation without session management
- **Secure by default**: Cryptographic token generation and validation
- **Protocol compliance**: Adhere to Mozilla Token Server API v1.0 specification
- **Extensible**: Support multiple OIDC providers through configuration

## Architecture

### High-Level Architecture

```
┌─────────────────┐
│ Firefox Sync    │
│ Client          │
└────────┬────────┘
         │ GET /1.0/sync/1.5
         │ Authorization: Bearer <OIDC_TOKEN>
         │ X-Client-State: <client_state>
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
│  │ - Validate X-Client-State        │  │
│  │ - Route to token endpoint        │  │
│  └──────────┬───────────────────────┘  │
│             │                           │
│  ┌──────────▼───────────────────────┐  │
│  │ OIDC Validator                   │  │
│  │ - Fetch JWKS from provider       │  │
│  │ - Verify token signature         │  │
│  │ - Validate claims (iss, aud, exp)│  │
│  │ - Validate timestamp (iat)       │  │
│  │ - Extract user identifier        │  │
│  └──────────┬───────────────────────┘  │
│             │                           │
│  ┌──────────▼───────────────────────┐  │
│  │ User Manager                     │  │
│  │ - Get/create user record         │  │
│  │ - Validate client state history  │  │
│  │ - Handle generation numbers      │  │
│  │ - Reset node allocation          │  │
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
│ - Client state history                  │
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

1. **Request Reception**: API Gateway receives GET request with OIDC token in Authorization header
2. **Token Validation**: Lambda validates OIDC token with provider's JWKS endpoint
3. **Timestamp Validation**: Lambda validates token timestamp against server time
4. **Client State Validation**: Lambda validates X-Client-State against history
5. **User Lookup**: Lambda queries DynamoDB for existing user record or creates new one
6. **Token Generation**: Generate HAWK credentials and construct api_endpoint dynamically
7. **Response**: Return JSON with id, key, uid, api_endpoint, and duration

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
- HTTP method is GET (per Mozilla spec)
- Path matches `/1.0/sync/1.5`
- Authorization header is present with Bearer scheme
- Accept header is acceptable (application/json)
- X-Client-State header format (if present): urlsafe-base64 alphabet + period, max 32 characters

**X-Client-State Handling**:
- Extract X-Client-State header from request (default to empty string if absent)
- Validate format: must be urlsafe-base64 characters (alphanumeric, underscore, hyphen) and period only, max 32 characters
- Pass to UserManager for client state history validation and generation increment logic

**Response Headers**:
- All 200 and 401 responses include `X-Timestamp` header with current Unix epoch seconds
- 503 responses include `Retry-After` header
- Any response may include `X-Backoff` header when server is under load
- 401 responses include `WWW-Authenticate` header

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
    def __init__(self, provider_url: str, client_id: str, clock_skew_tolerance: int = 300):
        """
        Initialize with OIDC provider configuration
        
        Args:
            provider_url: Base URL of OIDC provider
            client_id: Expected audience claim value
            clock_skew_tolerance: Maximum allowed clock skew in seconds (default 5 minutes)
        """
        pass
    
    def validate_token(self, token: str, server_time: int) -> OIDCTokenClaims:
        """
        Validate OIDC token and extract claims
        
        Args:
            token: Raw OIDC token string
            server_time: Current server timestamp for clock skew validation
            
        Returns:
            Validated token claims
            
        Raises:
            InvalidTokenError: If token is invalid
            InvalidTimestampError: If token timestamp differs too much from server time
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
6. Verify token has not expired (exp claim)
7. Validate token timestamp (iat claim) against server time with tolerance
8. Extract user identifier from `sub` claim

**Design Decision**: Use PyJWT library for token validation with JWKS support. Cache provider configuration and JWKS for 1 hour to reduce external API calls. Add timestamp validation with configurable clock skew tolerance.

**Rationale**: PyJWT is well-maintained, supports RS256 algorithm commonly used by OIDC providers, and handles JWKS fetching. Caching reduces latency and external dependencies while maintaining security (1-hour TTL allows for key rotation). Timestamp validation prevents replay attacks.

### 3. User Manager

**Responsibility**: Manage user records in DynamoDB, handle generation numbers for token invalidation, track client state history for key rotation

**Interface**:
```python
@dataclass
class UserRecord:
    user_id: str
    generation: int
    client_state: str
    client_state_history: List[str]
    created_at: float
    updated_at: float

class UserManager:
    def __init__(self, dynamodb_table, new_users_enabled: bool = True):
        """
        Initialize with DynamoDB table resource
        
        Args:
            dynamodb_table: boto3 DynamoDB table resource
            new_users_enabled: Whether to allow new user registration
        """
        pass
    
    def get_or_create_user(self, user_id: str, client_state: str = "") -> UserRecord:
        """
        Get existing user or create new record.
        Validates client state against history.
        If client_state differs from stored value, increment generation and reset node.
        
        Args:
            user_id: Unique user identifier from OIDC token
            client_state: X-Client-State header value (urlsafe-base64 + period, max 32 chars)
            
        Returns:
            User record with current generation number
            
        Raises:
            InvalidClientStateError: If client state is in history or empty when history exists
            NewUsersDisabledError: If new users are disabled and user doesn't exist
        """
        pass
    
    def validate_client_state(self, user_record: UserRecord, client_state: str) -> None:
        """
        Validate client state against history.
        
        Raises:
            InvalidClientStateError: If:
                - client_state matches any value in client_state_history
                - client_state is empty but client_state_history is not empty
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
```

**DynamoDB Schema**:
```
Table: TokenServerUsers
Partition Key: PK (String) = "USER#{user_id}"

Attributes:
- PK: String (partition key) = "USER#{user_id}" where user_id is OIDC sub claim
- user_id: String (OIDC sub claim - stable identifier)
- generation: Number (default: 0)
- client_state: String (default: "")
- client_state_history: List<String> (default: [])
- created_at: Number (timestamp)
- updated_at: Number (timestamp)

Note: uid is NOT stored - it is derived on-demand as hash(user_id + generation)
```

**Client State History Validation**:
Per Mozilla spec, the following client state transitions are rejected with "invalid-client-state":
1. New client_state matches any value in client_state_history
2. New client_state is empty but client_state_history contains non-empty values
3. Client state change without corresponding generation number increase (if IdP provides generation)

When a valid new client_state is accepted:
1. Add the previous client_state to client_state_history
2. Update client_state to the new value
3. Increment generation number
4. Reset node allocation (generate new uid and api_endpoint)

**Administrative Generation Increment**:
The `increment_generation()` method provides a mechanism for administrators to invalidate all tokens for a user during security events such as password resets or key rotation. This method can be invoked through:
- Direct DynamoDB update (for emergency scenarios)
- Administrative API endpoint (future enhancement)
- Automated security event handlers (e.g., triggered by identity provider webhooks)

When invoked, all previously issued tokens for the affected user become invalid immediately, as the Storage API validates the generation number embedded in the HAWK ID against the current value in DynamoDB.

**Node Assignment Strategy**:
- Node assignment is computed dynamically based on uid
- Format: `https://{base_url}/1.5/{uid}`
- Base URL from environment variable `STORAGE_BASE_URL`
- uid is regenerated when client_state changes (node reset)
- Constructed on-demand for each token response

**Design Decision**: Track client_state_history in DynamoDB to enforce Mozilla spec's client state transition rules. Regenerate uid when client_state changes to implement node allocation reset.

**Rationale**: The Mozilla spec requires rejecting client states that have been seen before, which prevents clients from reverting to old encryption keys. Node reset on client state change ensures data isolation when encryption keys change.

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
    
    def generate_uid(self, user_id: str, generation: int) -> int:
        """
        Generate numeric user ID from user identifier and generation.
        Changes when generation changes (node reset).
        
        Args:
            user_id: User identifier from OIDC sub claim
            generation: Current generation number
            
        Returns:
            Positive integer derived from user_id and generation hash
        """
        pass
```

**HAWK Credential Generation**:
- **HAWK ID**: Base64-encoded string containing `{user_id}:{generation}:{expiry_timestamp}`
- **HAWK Key**: 32 bytes of cryptographically random data, hex-encoded
- **Duration**: 300 seconds (5 minutes)
- **uid**: Hash of user_id + generation (changes on node reset)

**Design Decision**: Embed generation number and expiry in HAWK ID to enable stateless validation by Storage API. Use secrets.token_bytes() for cryptographic randomness. Include generation in uid calculation so uid changes when client_state changes.

**Rationale**: Stateless token design allows Storage API to validate tokens without querying Token Server. Embedding metadata in HAWK ID enables validation of generation number and expiry. uid changes on generation increment implement the Mozilla spec's node reset behavior.

**Note**: The Mozilla spec does not include `hashalg` in the response. We include it for HAWK compatibility but it's not part of the official spec.

### 5. Error Handler

**Responsibility**: Format error responses according to Mozilla Token Server API v1.0 specification

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
        errors: List[ErrorDetail],
        include_timestamp: bool = False,
        retry_after: Optional[int] = None,
        backoff: Optional[int] = None
    ) -> dict:
        """
        Format error response for API Gateway
        
        Args:
            status_code: HTTP status code
            error_type: Error type identifier (status field value)
            errors: List of error details
            include_timestamp: Whether to include X-Timestamp header
            retry_after: Retry-After header value (for 503)
            backoff: X-Backoff header value
            
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

**Standard Error Types (per Mozilla spec)**:
- `invalid-credentials`: Authentication failed due to invalid credentials (401)
- `invalid-timestamp`: Authentication failed due to timestamp skew (401)
- `invalid-generation`: Server has seen newer generation number (401)
- `invalid-client-state`: Invalid client state transition (401)
- `new-users-disabled`: New user registration is disabled (401)
- `invalid-request`: Malformed request (400)
- `not-found`: Endpoint not found (404)
- `method-not-allowed`: Wrong HTTP method (405)
- `not-acceptable`: Unsupported Accept header (406)
- `service-unavailable`: Backend service unreachable (503)

**Response Headers by Status Code**:
- 200: `X-Timestamp`, optionally `X-Backoff`
- 401: `X-Timestamp`, `WWW-Authenticate`
- 503: `Retry-After`, optionally `X-Backoff`
- Any: optionally `X-Backoff`

## Data Models

### User Record
```python
@dataclass
class UserRecord:
    user_id: str              # Unique identifier from OIDC sub claim (stable, used as PK)
    generation: int           # Monotonic counter for token invalidation
    client_state: str         # Current X-Client-State value (urlsafe-base64 + period, max 32 chars)
    client_state_history: List[str]  # Previously-seen client state values
    created_at: float         # Unix timestamp
    updated_at: float         # Unix timestamp
    # Note: uid is NOT stored - it's derived as hash(user_id + generation)
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
    uid: int              # Numeric user ID (hash of user_id + generation)
    duration: int         # Token validity (300 seconds)
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
- Properties 1.1, 2.5, 4.1, 4.2 all verify response structure - combined into Property 1
- Properties 3.3 and 6.7 both verify "invalid-generation" status - combined
- Properties 3.6 and 13.2 both verify client state change behavior - combined
- Properties 7.4 and 3.4 both verify new user defaults - combined
- Properties 14.1 and 14.2 can be combined into single X-Timestamp property

**New properties for Mozilla spec compliance:**
- HTTP method changed from POST to GET
- Added 406 Not Acceptable for unsupported Accept headers
- Added "invalid-timestamp", "invalid-generation", "invalid-client-state", "new-users-disabled" error statuses
- Added client_state_history tracking and validation
- Added Retry-After and X-Backoff headers
- Added WWW-Authenticate header on 401 responses
- X-Client-State format changed from hex-only to urlsafe-base64 + period

**Simplification: CORS Handling**
API Gateway handles all CORS configuration and OPTIONS requests automatically. This eliminates the need for Lambda to handle CORS.

### Correctness Properties

**Property 1: Complete token response structure**
*For any* valid OIDC token, the Token Server response SHALL contain all required fields: `id`, `key`, `api_endpoint`, `uid`, and `duration`.
**Validates: Requirements 1.1, 2.5, 4.1, 4.2**

**Property 2: OIDC token validation**
*For any* request with an OIDC token, the Token Server SHALL validate the token with the configured OIDC provider before issuing credentials.
**Validates: Requirements 1.2**

**Property 3: Invalid credentials rejection**
*For any* invalid OIDC token, the Token Server SHALL return a 401 status code with "invalid-credentials" status.
**Validates: Requirements 1.3, 6.4**

**Property 4: Malformed header rejection**
*For any* malformed Authorization header, the Token Server SHALL return a 400 status code with a validation error.
**Validates: Requirements 1.4**

**Property 5: Token duration consistency**
*For any* issued bearer token, the `duration` field SHALL equal 300 seconds.
**Validates: Requirements 1.5**

**Property 6: Node URL format**
*For any* token response, the `api_endpoint` SHALL match the format `https://{base_url}/1.5/{uid}`.
**Validates: Requirements 2.1, 2.3**

**Property 7: Node assignment consistency**
*For any* user with unchanged client_state, multiple token requests SHALL return the same `uid` and `api_endpoint`.
**Validates: Requirements 2.2**

**Property 8: Node reset on client state change**
*For any* user, when X-Client-State changes, the Token Server SHALL generate a new `uid` and `api_endpoint`.
**Validates: Requirements 2.4, 13.2**

**Property 9: Generation-based token invalidation**
*For any* user, when the generation number is incremented, all previously issued tokens SHALL be rejected with a 401 status code and "invalid-generation" status.
**Validates: Requirements 3.1, 3.3, 6.7**

**Property 10: Default generation number**
*For any* newly created user record, the generation number SHALL be 0 and client_state SHALL be empty.
**Validates: Requirements 3.4, 7.4**

**Property 11: Generation number monotonicity**
*For any* generation number update, the new value SHALL be greater than the previous value.
**Validates: Requirements 3.5**

**Property 12: Client state change increments generation**
*For any* request where X-Client-State differs from the previously stored value, the Token Server SHALL increment the user's generation number.
**Validates: Requirements 3.6**

**Property 13: HAWK ID format**
*For any* generated HAWK credentials, the `id` SHALL be a valid URL-safe base64-encoded string.
**Validates: Requirements 4.3**

**Property 14: HAWK key format and randomness**
*For any* generated HAWK credentials, the `key` SHALL be a 64-character hexadecimal string (32 bytes), and multiple generations SHALL produce unique keys.
**Validates: Requirements 4.4**

**Property 15: Missing Authorization rejection**
*For any* request without an Authorization header, the Token Server SHALL return a 401 status code.
**Validates: Requirements 5.1**

**Property 16: Invalid path rejection**
*For any* request to a path other than `/1.0/sync/1.5`, the Token Server SHALL return a 404 status code.
**Validates: Requirements 5.2**

**Property 17: Unsupported method rejection**
*For any* request with an HTTP method other than GET or OPTIONS, the Token Server SHALL return a 405 status code.
**Validates: Requirements 5.3**

**Property 18: Unacceptable Accept header rejection**
*For any* request with an unsupported Accept header, the Token Server SHALL return a 406 status code.
**Validates: Requirements 5.4**

**Property 19: Error message presence**
*For any* validation error, the response SHALL include a descriptive error message.
**Validates: Requirements 5.5**

**Property 20: Error response JSON validity**
*For any* error response, the response body SHALL be valid JSON with Content-Type application/json.
**Validates: Requirements 6.1**

**Property 21: Error response structure**
*For any* error response, the JSON SHALL contain a `status` field with the error type and an `errors` array with error details.
**Validates: Requirements 6.2, 6.3**

**Property 22: Validation error structure**
*For any* validation error, each object in the `errors` array SHALL contain `location`, `name`, and `description` fields.
**Validates: Requirements 6.5**

**Property 23: Timestamp skew rejection**
*For any* OIDC token with timestamp significantly different from server time, the Token Server SHALL return a 401 status code with "invalid-timestamp" status.
**Validates: Requirements 6.6, 18.2**

**Property 24: Invalid client state status**
*For any* invalid client state transition, the Token Server SHALL return a 401 status code with "invalid-client-state" status.
**Validates: Requirements 6.8, 13.6, 13.7**

**Property 25: New users disabled status**
*For any* new user when registration is disabled, the Token Server SHALL return a 401 status code with "new-users-disabled" status.
**Validates: Requirements 6.9, 17.2**

**Property 26: User record DynamoDB structure**
*For any* created user record, the record SHALL be stored in DynamoDB with `user_id` as the partition key.
**Validates: Requirements 7.1**

**Property 27: User record required fields**
*For any* stored user record, the record SHALL include `user_id`, `generation`, `client_state`, `client_state_history`, `created_at`, and `updated_at` fields.
**Validates: Requirements 7.2**

**Property 28: Updated timestamp modification**
*For any* user record update, the `updated_at` timestamp SHALL be greater than the previous value.
**Validates: Requirements 7.5**

**Property 29: Client state history tracking**
*For any* client state change, the Token Server SHALL add the previous client_state to client_state_history.
**Validates: Requirements 7.6, 13.8**

**Property 30: OIDC signature verification**
*For any* OIDC token validation, the Token Server SHALL verify the token signature using the provider's JWKS endpoint.
**Validates: Requirements 9.3**

**Property 31: OIDC issuer validation**
*For any* OIDC token, the Token Server SHALL reject tokens where the issuer does not match the configured OIDC provider.
**Validates: Requirements 9.4**

**Property 32: OIDC audience validation**
*For any* OIDC token, the Token Server SHALL reject tokens where the audience does not match the expected client ID.
**Validates: Requirements 9.5**

**Property 33: OIDC provider unreachable error**
*For any* request when the OIDC provider is unreachable, the Token Server SHALL return a 503 status code with a service unavailable error.
**Validates: Requirements 10.5**

**Property 34: User identifier extraction**
*For any* OIDC token, the Token Server SHALL extract the user identifier from the `sub` claim.
**Validates: Requirements 11.1**

**Property 35: Token expiry validation**
*For any* OIDC token validation, the Token Server SHALL reject expired tokens (based on `exp` claim) with a 401 status code.
**Validates: Requirements 11.2, 11.3**

**Property 36: Missing user identifier rejection**
*For any* OIDC token without a `sub` claim, the Token Server SHALL return a 401 status code.
**Validates: Requirements 11.4**

**Property 37: Successful authentication logging**
*For any* successful token issuance, the Token Server SHALL log the user identifier and timestamp.
**Validates: Requirements 12.1**

**Property 38: Failed authentication logging**
*For any* authentication failure, the Token Server SHALL log the failure reason and timestamp.
**Validates: Requirements 12.2**

**Property 39: Sensitive data exclusion from logs**
*For any* log entry, the Token Server SHALL NOT include bearer tokens, HAWK keys, or other sensitive credentials.
**Validates: Requirements 12.5**

**Property 40: X-Client-State storage**
*For any* request with an X-Client-State header, the Token Server SHALL store the client state value with the user record.
**Validates: Requirements 13.1**

**Property 41: X-Client-State default value**
*For any* request without an X-Client-State header, the Token Server SHALL use an empty string as the default value.
**Validates: Requirements 13.3**

**Property 42: X-Client-State format validation**
*For any* X-Client-State header value, the Token Server SHALL validate it contains only urlsafe-base64 characters (alphanumeric, underscore, hyphen) and period, up to 32 characters.
**Validates: Requirements 13.4**

**Property 43: Invalid X-Client-State rejection**
*For any* request with an invalid X-Client-State format, the Token Server SHALL return a 400 status code with a validation error.
**Validates: Requirements 13.5**

**Property 44: Previously-seen client state rejection**
*For any* request with an X-Client-State that matches a value in client_state_history, the Token Server SHALL return a 401 status code with "invalid-client-state" status.
**Validates: Requirements 13.6**

**Property 45: Empty client state with history rejection**
*For any* request with empty X-Client-State when client_state_history contains non-empty values, the Token Server SHALL return a 401 status code with "invalid-client-state" status.
**Validates: Requirements 13.7**

**Property 46: X-Timestamp header on 200 responses**
*For any* successful (200) response, the Token Server SHALL include an X-Timestamp header with the current server time in seconds since epoch.
**Validates: Requirements 14.1**

**Property 47: X-Timestamp header on 401 responses**
*For any* 401 error response, the Token Server SHALL include an X-Timestamp header with the current server time in seconds since epoch.
**Validates: Requirements 14.2**

**Property 48: X-Timestamp format**
*For any* X-Timestamp header value, the value SHALL be an integer representing Unix epoch seconds (POSIX timestamp).
**Validates: Requirements 14.3**

**Property 49: Retry-After header on 503**
*For any* 503 response, the Token Server SHALL include a Retry-After header with the number of seconds to wait.
**Validates: Requirements 15.1**

**Property 50: X-Backoff header support**
*For any* response when server is under load, the Token Server MAY include an X-Backoff header with the number of seconds to avoid unnecessary requests.
**Validates: Requirements 15.2, 15.3**

**Property 51: WWW-Authenticate header on 401**
*For any* 401 response, the Token Server SHALL include a WWW-Authenticate header indicating supported authentication schemes.
**Validates: Requirements 16.1, 16.2, 16.3**

**Property 52: New users disabled configuration**
*For any* request from an unknown user when new user registration is disabled, the Token Server SHALL reject the request.
**Validates: Requirements 17.1**

**Property 53: Timestamp validation with tolerance**
*For any* OIDC token, the Token Server SHALL validate the token's issued-at (iat) claim against server time with configurable tolerance.
**Validates: Requirements 18.1, 18.4**

**Property 54: Timestamp validation includes X-Timestamp**
*For any* timestamp validation failure, the response SHALL include X-Timestamp header to help client adjust clock.
**Validates: Requirements 18.3**

## Error Handling

### Error Categories

**1. Authentication Errors (401)**
- `invalid-credentials`: Invalid OIDC token signature, expired token, wrong issuer/audience, missing sub claim
- `invalid-timestamp`: Token timestamp differs too much from server time
- `invalid-generation`: Server has seen newer generation number
- `invalid-client-state`: Invalid client state transition (reused or empty when history exists)
- `new-users-disabled`: New user registration is disabled

**2. Validation Errors (400)**
- Malformed request body
- Invalid JSON payload
- Missing required fields
- Malformed Authorization header format
- Invalid X-Client-State format

**3. Not Found Errors (404)**
- Invalid endpoint path
- Unsupported API version

**4. Method Not Allowed (405)**
- Using POST, PUT, DELETE, etc. on token endpoint (only GET allowed)

**5. Not Acceptable (406)**
- Unsupported Accept header

**6. Service Unavailable (503)**
- OIDC provider unreachable
- DynamoDB connection failure
- Temporary service degradation

### Error Response Format

All errors follow the Mozilla Token Server API v1.0 format (Cornice-style):

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

### Response Headers by Error Type

| Status Code | X-Timestamp | WWW-Authenticate | Retry-After | X-Backoff |
|-------------|-------------|------------------|-------------|-----------|
| 200         | Yes         | No               | No          | Optional  |
| 400         | No          | No               | No          | Optional  |
| 401         | Yes         | Yes              | No          | Optional  |
| 404         | No          | No               | No          | Optional  |
| 405         | No          | No               | No          | Optional  |
| 406         | No          | No               | No          | Optional  |
| 503         | No          | No               | Yes         | Optional  |

### Error Handling Strategy

**Design Decision**: Implement centralized error handling middleware that catches exceptions and formats them according to the Mozilla spec.

**Rationale**: Centralized error handling ensures consistent error responses across all endpoints and simplifies maintenance.

**Implementation Approach**:
1. Define custom exception classes for each error category
2. Implement error handler that catches exceptions and formats responses
3. Include request context in error logs (request ID, user ID if available)
4. Sanitize error messages to avoid leaking sensitive information
5. Add appropriate headers based on error type

### Retry Strategy

**For OIDC Provider Calls**:
- Retry up to 3 times with exponential backoff (100ms, 200ms, 400ms)
- Return 503 with Retry-After header if all retries fail
- Cache successful JWKS responses for 1 hour

**For DynamoDB Operations**:
- Use boto3 default retry strategy (exponential backoff)
- Return 503 with Retry-After header for persistent failures
- Log all retry attempts for monitoring

## Testing Strategy

### Unit Testing

**Framework**: pytest with pytest-mock for mocking external dependencies

**Coverage Goals**:
- 90%+ code coverage for all components
- 100% coverage for critical paths (token generation, validation)

**Key Unit Tests**:
1. **Request Handler Tests**
   - Valid GET request handling
   - Invalid HTTP method rejection (POST, PUT, DELETE → 405)
   - Missing Authorization header handling
   - Malformed request handling
   - Accept header validation (406)

2. **OIDC Validator Tests**
   - Valid token validation
   - Expired token rejection
   - Invalid signature rejection
   - Wrong issuer/audience rejection
   - Timestamp skew rejection
   - JWKS fetching and caching

3. **User Manager Tests**
   - New user creation with defaults
   - Existing user retrieval
   - Generation number increment
   - Client state history validation
   - Node reset on client state change
   - New users disabled rejection

4. **Token Generator Tests**
   - HAWK ID generation and format
   - HAWK key randomness and format
   - Token response structure
   - Duration field value
   - uid changes on generation change

5. **Error Handler Tests**
   - Error response formatting
   - Status code mapping
   - Error detail structure
   - Header inclusion by error type

### Property-Based Testing

**Framework**: Hypothesis (Python property-based testing library)

**Configuration**: Each property-based test will run a minimum of 100 iterations to ensure comprehensive coverage of the input space.

**Test Tagging**: Each property-based test MUST be tagged with a comment explicitly referencing the correctness property from the design document using this format: `# Feature: token-server, Property {number}: {property_text}`

### Integration Testing

**Scope**: Test complete request flow from API Gateway event to response

**Key Integration Tests**:
1. End-to-end token issuance with real OIDC token validation (using test provider)
2. Token invalidation flow (issue token, increment generation, verify rejection)
3. First-time user flow (no existing record → create user → token issuance)
4. Returning user flow (existing record → same node → token issuance)
5. Client state change flow (change state → node reset → new uid)
6. Client state history rejection (reuse old state → 401)
7. New users disabled flow (disable → reject new user → 401)
8. Error scenarios with real AWS services (DynamoDB, OIDC provider)

**Test Environment**:
- Use LocalStack for DynamoDB testing
- Mock OIDC provider with test JWKS endpoint
- Use pytest fixtures for test data setup

### CORS Testing

**Note**: CORS is handled entirely by API Gateway configuration, not Lambda code. Therefore:
- Lambda unit tests do not need to verify CORS headers
- Lambda integration tests do not need to test OPTIONS request handling
- CORS functionality should be verified through infrastructure tests or manual testing of the deployed API Gateway
- Requirements 8.1-8.5 are satisfied through API Gateway configuration, not Lambda implementation

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
- Verify issued-at timestamp with tolerance (prevents replay attacks)
- Extract user identifier from `sub` claim only after validation

### Client State Security

**History Tracking**:
- Maintain list of previously-seen client states
- Reject attempts to revert to old client states
- Prevent clients from reverting to old encryption keys

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

**X-Client-State Validation**:
- Validate format: urlsafe-base64 alphabet + period only
- Maximum length: 32 characters
- Validate against history before accepting

## Performance Considerations

### Latency Optimization

**Target Latency**: < 200ms for token issuance (p95)

**Optimization Strategies**:
1. **JWKS Caching**: Cache OIDC provider JWKS for 1 hour to avoid repeated fetches
2. **Provider Config Caching**: Cache OpenID configuration for 1 hour
3. **DynamoDB Optimization**: Use consistent reads only when necessary
4. **Connection Pooling**: Reuse HTTP connections for OIDC provider calls
5. **Lambda Warm-up**: Keep Lambda instances warm with periodic health checks

### Scalability

**Concurrency**:
- Lambda auto-scales to handle concurrent requests
- DynamoDB on-demand pricing scales automatically
- No shared state between requests enables horizontal scaling

**Rate Limiting**:
- Implement at API Gateway level (not in Lambda)
- Return 429 status code when limit exceeded
- Use X-Backoff header to signal load

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
- `NEW_USERS_ENABLED`: Whether to allow new user registration (default: true)
- `CLOCK_SKEW_TOLERANCE`: Maximum allowed clock skew in seconds (default: 300)
- `RETRY_AFTER_SECONDS`: Default Retry-After value for 503 responses (default: 30)

### OIDC Secret Configuration

The OIDC configuration is stored in AWS Secrets Manager with the name `ffsync-oidc-config-{stage}`.

**Secret JSON Structure**:
```json
{
  "provider_url": "https://auth.example.com",
  "client_id": "your-client-id"
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
- REST API
- CORS configuration at API Gateway level
- Allow-Methods: `GET, OPTIONS`
- Request validation enabled
- CloudWatch logging enabled

## Appendix

### References

- [Mozilla Token Server API v1.0](https://mozilla-services.readthedocs.io/en/latest/token/apis.html)
- [HAWK Authentication Scheme](https://github.com/mozilla/hawk)
- [OpenID Connect Core Specification](https://openid.net/specs/openid-connect-core-1_0.html)
- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)
