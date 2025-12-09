# Implementation Plan

- [x] 1. Set up Token Server dependencies and directory structure
  - Add PyJWT>=2.8.0 to lambda/requirements.txt for OIDC token validation
  - Add hypothesis>=6.0.0 to lambda/requirements-dev.txt for property-based testing
  - Add python-jose[cryptography]>=3.3.0 to lambda/requirements.txt for JWKS support
  - Add requests>=2.31.0 to lambda/requirements.txt for OIDC provider HTTP calls
  - _Requirements: All_

- [x] 2. Implement core data models
  - Create lambda/src/shared/user.py with UserRecord dataclass (user_id, generation, created_at, updated_at)
  - Create lambda/src/shared/oidc.py with OIDCTokenClaims (sub, iss, aud, exp, iat) and OIDCProviderConfig (issuer, jwks_uri, etc.) dataclasses
  - Create lambda/src/shared/token.py with TokenResponse dataclass (id, key, api_endpoint, uid, duration, hashalg)
  - Create lambda/src/shared/exceptions.py with custom exception classes (InvalidTokenError, InvalidCredentialsError, etc.) and ErrorDetail dataclass
  - _Requirements: 1.1, 4.1, 4.2, 7.2, 9.2, 11.1_

- [x] 3. Implement OIDC Validator component
  - Create lambda/src/services/oidc_validator.py with OIDCValidator class
  - Implement discover_provider_config() to fetch .well-known/openid-configuration
  - Implement JWKS fetching and caching (1-hour TTL using functools.lru_cache)
  - Implement validate_token() with signature verification using PyJWT
  - Implement issuer validation against configured provider
  - Implement audience validation against configured client_id
  - Implement expiry validation using exp claim
  - Extract user identifier from sub claim
  - Add TTL-based cache invalidation for provider configuration (refresh before expiry)
  - _Requirements: 1.2, 9.2, 9.3, 9.4, 9.5, 10.4, 11.1, 11.2_

- [ ]* 3.1 Write property test for OIDC token validation
  - **Property 2: OIDC token validation**
  - **Validates: Requirements 1.2**

- [ ]* 3.2 Write property test for invalid token rejection
  - **Property 3: Invalid credentials rejection**
  - **Validates: Requirements 1.3**

- [ ]* 3.3 Write property test for issuer validation
  - **Property 25: OIDC issuer validation**
  - **Validates: Requirements 9.4**

- [ ]* 3.4 Write property test for audience validation
  - **Property 26: OIDC audience validation**
  - **Validates: Requirements 9.5**

- [ ]* 3.5 Write property test for token expiry validation
  - **Property 29: Token expiry validation**
  - **Validates: Requirements 11.2, 11.3**

- [ ]* 3.6 Write property test for missing sub claim rejection
  - **Property 30: Missing user identifier rejection**
  - **Validates: Requirements 11.4**

- [ ]* 3.7 Write property test for OIDC signature verification
  - **Property 24: OIDC signature verification**
  - **Validates: Requirements 9.3**

- [x] 4. Implement User Manager component
  - Create lambda/src/services/user_manager.py with UserManager class
  - Initialize with DynamoDB table resource (similar to StorageManager pattern)
  - Implement get_or_create_user() with conditional writes
  - Set default generation to 0 for new users
  - Implement increment_generation() with atomic counter update using UpdateExpression
  - Implement validate_generation() to check current value
  - Update updated_at timestamp on all modifications
  - Handle DynamoDB exceptions (ClientError, etc.)
  - _Requirements: 3.1, 3.2, 3.4, 3.5, 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ]* 4.1 Write property test for new user generation number
  - **Property 9: Default generation number**
  - **Validates: Requirements 3.4, 7.4**

- [ ]* 4.2 Write property test for generation number monotonicity
  - **Property 10: Generation number monotonicity**
  - **Validates: Requirements 3.5**

- [ ]* 4.3 Write property test for generation-based invalidation
  - **Property 7: Generation-based token invalidation**
  - **Validates: Requirements 3.1, 3.3**

- [ ]* 4.4 Write property test for updated timestamp modification
  - **Property 23: Updated timestamp modification**
  - **Validates: Requirements 7.5**

- [x] 5. Implement Token Generator component
  - Create lambda/src/services/token_generator.py with TokenGenerator class
  - Implement generate_hawk_id() encoding user_id:generation:expiry as base64
  - Implement generate_hawk_key() using secrets.token_bytes(32) and hex encoding
  - Implement generate_token() to construct complete TokenResponse
  - Compute api_endpoint dynamically as {base_url}/1.5/{user_id}
  - Set duration to 300 seconds
  - Set hashalg to "sha256"
  - Generate uid as hash of user_id (using hashlib)
  - _Requirements: 1.1, 1.5, 2.1, 2.2, 2.3, 2.5, 4.1, 4.2, 4.3, 4.4_

- [ ]* 5.1 Write property test for complete token response structure
  - **Property 1: Complete token response structure**
  - **Validates: Requirements 1.1, 2.5, 4.1, 4.2**

- [ ]* 5.2 Write property test for token duration consistency
  - **Property 5: Token duration consistency**
  - **Validates: Requirements 1.5**

- [ ]* 5.3 Write property test for node URL format
  - **Property 6: Node URL format**
  - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**

- [ ]* 5.4 Write property test for HAWK ID format
  - **Property 11: HAWK ID format**
  - **Validates: Requirements 4.3**

- [ ]* 5.5 Write property test for HAWK key format and randomness
  - **Property 12: HAWK key format and randomness**
  - **Validates: Requirements 4.4**

- [ ]* 5.6 Write property test for user identifier consistency
  - **Property 31: User identifier consistency**
  - **Validates: Requirements 11.5**

- [x] 6. Implement Token Request Handler
  - Create lambda/src/services/token_handler.py with TokenHandler class
  - Implement handle() method that orchestrates the token issuance flow
  - Implement validate_request() for HTTP method, path, headers
  - Parse Authorization header and extract Bearer token
  - Validate HTTP method is POST
  - Validate path matches /1.0/sync/1.5
  - Coordinate between OIDCValidator, UserManager, and TokenGenerator
  - Return API Gateway proxy response dict with JSON body
  - Format success response with id, key, api_endpoint, uid, duration, hashalg fields
  - Format error responses in Firefox Sync protocol format (status, errors array)
  - _Requirements: 1.1, 1.3, 1.4, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ]* 6.1 Write property test for malformed header rejection
  - **Property 4: Malformed header rejection**
  - **Validates: Requirements 1.4**

- [ ]* 6.2 Write property test for invalid path rejection
  - **Property 13: Invalid path rejection**
  - **Validates: Requirements 5.2**

- [ ]* 6.3 Write property test for unsupported method rejection
  - **Property 14: Unsupported method rejection**
  - **Validates: Requirements 5.3**

- [ ]* 6.4 Write property test for invalid content type rejection
  - **Property 15: Invalid content type rejection**
  - **Validates: Requirements 5.4**

- [ ]* 6.5 Write property test for error message presence
  - **Property 16: Error message presence**
  - **Validates: Requirements 5.5**

- [ ]* 6.6 Write property test for error response JSON validity
  - **Property 17: Error response JSON validity**
  - **Validates: Requirements 6.1**

- [ ]* 6.7 Write property test for error response structure
  - **Property 18: Error response structure**
  - **Validates: Requirements 6.2, 6.3**

- [ ]* 6.8 Write property test for 401 error status value
  - **Property 19: 401 error status value**
  - **Validates: Requirements 6.4**

- [ ]* 6.9 Write property test for validation error structure
  - **Property 20: Validation error structure**
  - **Validates: Requirements 6.5**

- [ ] 7. Implement structured logging
  - Configure AWS Lambda Powertools Logger with JSON formatter
  - Implement log_successful_authentication() with user_id and timestamp
  - Implement log_failed_authentication() with reason and timestamp
  - Implement log_validation_error() with error details
  - Ensure no sensitive data (tokens, keys) in logs
  - Add structured fields for correlation (request_id, user_id)
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [ ]* 7.1 Write property test for successful authentication logging
  - **Property 32: Successful authentication logging**
  - **Validates: Requirements 12.1**

- [ ]* 7.2 Write property test for failed authentication logging
  - **Property 33: Failed authentication logging**
  - **Validates: Requirements 12.2**

- [ ]* 7.3 Write property test for validation error logging
  - **Property 34: Validation error logging**
  - **Validates: Requirements 12.3**

- [ ]* 7.4 Write property test for structured logging format
  - **Property 35: Structured logging format**
  - **Validates: Requirements 12.4**

- [ ]* 7.5 Write property test for sensitive data exclusion from logs
  - **Property 36: Sensitive data exclusion from logs**
  - **Validates: Requirements 12.5**

- [ ] 8. Wire Token Server entrypoint and components
  - Update lambda/src/entrypoint/token_api.py to implement token_handler() function
  - Add TokenServiceProvider properties to lambda/src/environment/service_provider.py
  - Initialize TokenHandler with dependencies from environment variables
  - Environment variables: OIDC_SECRET_ARN (Secrets Manager secret containing provider_url and client_id), BASE_DOMAIN, TOKEN_USERS_TABLE_NAME
  - Fetch OIDC config from Secrets Manager and cache it
  - Use cached_property pattern for lazy initialization (like existing ServiceProvider)
  - Implement request flow: validate → authenticate → get/create user → generate token → respond
  - Add error handling with appropriate HTTP status codes
  - Add retry logic for OIDC provider calls (3 retries with exponential backoff using tenacity or manual retry)
  - _Requirements: 1.1, 1.2, 1.3, 10.1, 10.2, 10.3, 10.5_

- [ ]* 8.1 Write property test for OIDC provider unreachable error
  - **Property 27: OIDC provider unreachable error**
  - **Validates: Requirements 10.5**

- [ ]* 8.2 Write property test for user identifier extraction
  - **Property 28: User identifier extraction**
  - **Validates: Requirements 11.1**

- [ ] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Create Smithy model for Token Server
  - Create smithy/models/token/token.smithy with TokenService definition
  - Define GetToken operation with POST /1.0/sync/1.5 endpoint
  - Define GetTokenInput structure with Authorization header
  - Define GetTokenOutput structure with id, key, api_endpoint, uid, duration, hashalg fields
  - Define error structures: InvalidCredentialsError, ValidationError, ServiceUnavailableError
  - Add @restJson1 protocol and AWS API Gateway integration traits
  - _Requirements: 1.1, 1.3, 5.1, 5.2, 6.1, 6.2_

- [x] 11. Update Smithy build configuration
  - Modify smithy/smithy-build.json to use projections
  - Create "storage" projection for existing StorageService
  - Create "token" projection for new TokenService
  - Both projections use openapi plugin with respective service references
  - Verify build generates: build/smithy/storage/openapi/ and build/smithy/token/openapi/
  - _Requirements: All_

- [x] 12. Create DynamoDB table for Token Users in CDK
  - Add buildTokenUsersTable() method to ServiceStack
  - Set partition key as PK (String) to match existing table patterns
  - Configure on-demand billing mode
  - Enable encryption at rest (AWS_MANAGED)
  - Enable point-in-time recovery
  - Follow existing table naming pattern: ffsync-token-users-{stage}
  - _Requirements: 7.1, 7.2_

- [x] 13. Update Token Server Lambda environment variables in CDK
  - Add environment variables to buildTokenApiHandler(): OIDC_SECRET_ARN (Secrets Manager secret containing provider_url and client_id), BASE_DOMAIN, TOKEN_USERS_TABLE_NAME
  - Reference Secrets Manager secret `ffsync-oidc-config-{stage}` for OIDC configuration
  - Grant Secrets Manager read permissions to Lambda via `oidcSecret.grantRead(fn)`
  - Grant DynamoDB read/write permissions to TokenUsersTable
  - _Requirements: 10.1, 10.2, 10.3_

- [x] 14. Token Server API Gateway (already implemented)
  - Token API Gateway created in buildApi() method using Service.TOKEN
  - OpenAPI spec loaded from build/smithy/token/openapi/TokenService.openapi.json
  - Custom domain: token.{stage}.{BASE_DOMAIN}
  - Certificate and DNS records configured
  - CloudWatch logging enabled with MethodLoggingLevel.INFO
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 15. Storage API configuration (already implemented)
  - Storage API uses build/smithy/storage/openapi/ path
  - Storage API uses sync.{stage}.{BASE_DOMAIN} domain
  - Both APIs coexist with separate domains via Service enum
  - _Requirements: N/A (infrastructure maintenance)_

- [ ] 16. Write integration tests

- [ ]* 16.1 Write integration test for end-to-end token issuance
  - Test complete flow from API Gateway event to token response
  - Use mocked OIDC provider and mocked DynamoDB using botocore Stubber
  - Verify token structure and validity
  - _Requirements: 1.1, 1.2_

- [ ]* 16.2 Write integration test for token invalidation flow
  - Issue token, increment generation, verify rejection
  - _Requirements: 3.1, 3.2, 3.3_

- [ ]* 16.3 Write integration test for first-time user flow
  - No existing record → create user → assign node → issue token
  - _Requirements: 2.1, 3.4, 7.4_

- [ ]* 16.4 Write integration test for returning user flow
  - Existing record → same node → issue token
  - _Requirements: 2.2, 2.4_

- [ ] 17. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
