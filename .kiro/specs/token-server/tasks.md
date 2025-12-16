# Implementation Plan

## Phase 1: Previously Completed Tasks (Reference)

- [x] 1. Set up Token Server dependencies and directory structure
  - _Requirements: All_

- [x] 2. Implement core data models
  - _Requirements: 1.1, 4.1, 4.2, 7.2, 9.2, 11.1, 13.1_

- [x] 3. Implement OIDC Validator component
  - _Requirements: 1.2, 9.2, 9.3, 9.4, 9.5, 10.4, 11.1, 11.2_

- [x] 4. Implement User Manager component
  - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.7, 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 5. Implement Token Generator component
  - _Requirements: 1.1, 1.5, 2.1, 2.2, 2.3, 2.5, 4.1, 4.2, 4.3, 4.4_

- [x] 6. Implement Token Request Handler
  - _Requirements: 1.1, 1.3, 1.4, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 7. Wire Token Server entrypoint and ServiceProvider
  - _Requirements: 1.1, 1.2, 1.3, 10.1, 10.2, 10.3, 10.5_

- [x] 8. Add X-Client-State support to User Manager
  - _Requirements: 13.1, 13.2, 13.3, 3.6_

- [x] 9. Add X-Client-State and X-Timestamp headers
  - _Requirements: 13.4, 13.5, 14.1, 14.2, 14.3_

- [x] 10. Checkpoint - Ensure all tests pass

- [x] 11. Create Smithy model for Token Server
  - _Requirements: 1.1, 1.3, 5.1, 5.2, 6.1, 6.2_

- [x] 12. Update Smithy build configuration
  - _Requirements: All_

- [x] 13. Create DynamoDB table for Token Users in CDK
  - _Requirements: 7.1, 7.2_

- [x] 14. Update Token Server Lambda environment variables in CDK
  - _Requirements: 10.1, 10.2, 10.3_

- [x] 15. Token Server API Gateway (already implemented)
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 16. Storage API configuration (already implemented)

- [x] 17. Change HTTP method from POST to GET
  - [x] 17.1 Update Smithy model to use GET instead of POST
    - _Requirements: 1.1_
  - [x] 17.2 Update Request Handler for GET method
    - _Requirements: 1.1_
  - [x] 17.3 Update unit tests for GET method
    - _Requirements: 1.1_

## Phase 2: Mozilla Spec Compliance Updates

- [x] 18. Add new error exception classes
  - [x] 18.1 Add InvalidTimestampError exception
    - Create exception class in lambda/src/shared/exceptions.py
    - Map to 401 status with "invalid-timestamp" status
    - _Requirements: 6.6, 18.2_
  - [x] 18.2 Add InvalidGenerationError exception
    - Create exception class in lambda/src/shared/exceptions.py
    - Map to 401 status with "invalid-generation" status
    - _Requirements: 3.3, 6.7_
  - [x] 18.3 Add InvalidClientStateError exception
    - Create exception class in lambda/src/shared/exceptions.py
    - Map to 401 status with "invalid-client-state" status
    - _Requirements: 6.8, 13.6, 13.7_
  - [x] 18.4 Add NewUsersDisabledError exception
    - Create exception class in lambda/src/shared/exceptions.py
    - Map to 401 status with "new-users-disabled" status
    - _Requirements: 6.9, 17.2_
  - [x] 18.5 Update Request Handler error mapping
    - Add exception handlers for new error types
    - Return correct status codes and status field values
    - _Requirements: 6.6, 6.7, 6.8, 6.9_
  - [x] 18.6 Add unit tests for new error statuses
    - Test each new error type returns correct status code and status field
    - _Requirements: 6.6, 6.7, 6.8, 6.9_

- [ ]* 18.7 Write property test for invalid-timestamp status
  - **Property 23: Timestamp skew rejection**
  - **Validates: Requirements 6.6, 18.2**

- [ ]* 18.8 Write property test for invalid-generation status
  - **Property 9: Generation-based token invalidation**
  - **Validates: Requirements 3.3, 6.7**

- [ ]* 18.9 Write property test for invalid-client-state status
  - **Property 24: Invalid client state status**
  - **Validates: Requirements 6.8**

- [ ]* 18.10 Write property test for new-users-disabled status
  - **Property 25: New users disabled status**
  - **Validates: Requirements 6.9, 17.2**

- [x] 19. Update X-Client-State validation to urlsafe-base64 + period
  - [x] 19.1 Update validation regex pattern in Request Handler
    - Change CLIENT_STATE_PATTERN from `^[a-fA-F0-9]{0,32}$` to `^[a-zA-Z0-9_.-]{0,32}$`
    - Update error message to reflect new allowed characters (urlsafe-base64 + period)
    - _Requirements: 13.4_
  - [x] 19.2 Update Smithy model pattern
    - Change @pattern in smithy/models/common.smithy from `^[a-fA-F0-9]*$` to `^[a-zA-Z0-9_.-]*$`
    - Rebuild Smithy models
    - _Requirements: 13.4_
  - [x] 19.3 Update unit tests for new validation
    - Add tests for valid urlsafe-base64 characters (alphanumeric, underscore, hyphen, period)
    - Update invalid format tests
    - _Requirements: 13.4_

- [ ]* 19.4 Write property test for X-Client-State format validation
  - **Property 42: X-Client-State format validation**
  - **Validates: Requirements 13.4**

- [x] 20. Add client_state_history tracking
  - [x] 20.1 Update UserRecord dataclass
    - Add client_state_history: List[str] field to lambda/src/shared/user.py
    - Default to empty list for new users
    - _Requirements: 7.2, 7.6_
  - [x] 20.2 Update DynamoDB schema handling in UserManager
    - Update create_user() to initialize client_state_history as empty list
    - Update get_user() to read client_state_history from DynamoDB
    - Handle migration for existing records (default to empty list if missing)
    - _Requirements: 7.2, 7.6_
  - [x] 20.3 Implement history validation in UserManager
    - Add validate_client_state() method
    - Reject if new client_state matches any value in history
    - Reject if new client_state is empty but history contains non-empty values
    - _Requirements: 13.6, 13.7_
  - [x] 20.4 Update get_or_create_user() for history tracking
    - Call validate_client_state() before accepting new state
    - Add previous client_state to history when state changes
    - _Requirements: 13.8_
  - [x] 20.5 Add unit tests for history validation
    - Test rejection of previously-seen client state
    - Test rejection of empty state when history exists
    - Test history is updated on state change
    - _Requirements: 13.6, 13.7, 13.8_

- [ ]* 20.6 Write property test for previously-seen client state rejection
  - **Property 44: Previously-seen client state rejection**
  - **Validates: Requirements 13.6**

- [ ]* 20.7 Write property test for empty client state with history rejection
  - **Property 45: Empty client state with history rejection**
  - **Validates: Requirements 13.7**

- [ ]* 20.8 Write property test for client state history tracking
  - **Property 29: Client state history tracking**
  - **Validates: Requirements 7.6, 13.8**

- [x] 21. Add timestamp validation for OIDC tokens
  - [x] 21.1 Add clock_skew_tolerance configuration
    - Add CLOCK_SKEW_TOLERANCE environment variable (default 300 seconds)
    - Add to ServiceProvider configuration
    - _Requirements: 18.4_
  - [x] 21.2 Update OIDCValidator for timestamp validation
    - Add clock_skew_tolerance parameter to __init__()
    - Add server_time parameter to validate_token()
    - Validate iat claim against server time with tolerance
    - Raise InvalidTimestampError if skew exceeds tolerance
    - _Requirements: 18.1, 18.2_
  - [x] 21.3 Update Request Handler to pass server time
    - Pass current server time to OIDCValidator.validate_token()
    - Include X-Timestamp in response on timestamp validation failure
    - _Requirements: 18.3_
  - [x] 21.4 Add unit tests for timestamp validation
    - Test valid timestamps within tolerance
    - Test rejection of timestamps outside tolerance
    - Test X-Timestamp header included on failure
    - _Requirements: 18.1, 18.2, 18.3, 18.4_

- [ ]* 21.5 Write property test for timestamp validation
  - **Property 53: Timestamp validation with tolerance**
  - **Validates: Requirements 18.1, 18.4**

- [ ]* 21.6 Write property test for timestamp failure includes X-Timestamp
  - **Property 54: Timestamp validation includes X-Timestamp**
  - **Validates: Requirements 18.3**

- [ ] 22. Add Retry-After header on 503 responses
  - [ ] 22.1 Add RETRY_AFTER_SECONDS configuration
    - Add environment variable (default 30 seconds)
    - Add to ServiceProvider configuration
    - _Requirements: 15.1_
  - [ ] 22.2 Update error response for 503 status
    - Add Retry-After header to all 503 responses in _error_response()
    - _Requirements: 15.1_
  - [ ] 22.3 Add unit tests for Retry-After header
    - Test 503 responses include Retry-After header
    - Test header value is correct
    - _Requirements: 15.1_

- [ ]* 22.4 Write property test for Retry-After on 503
  - **Property 49: Retry-After header on 503**
  - **Validates: Requirements 15.1**

- [ ] 23. Add WWW-Authenticate header on 401 responses
  - [ ] 23.1 Update error response for 401 status
    - Add WWW-Authenticate header with "Bearer" scheme to all 401 responses
    - Include realm and error description
    - _Requirements: 16.1, 16.2, 16.3_
  - [ ] 23.2 Add unit tests for WWW-Authenticate header
    - Test all 401 responses include WWW-Authenticate header
    - Test header format is correct (Bearer scheme)
    - _Requirements: 16.1, 16.2, 16.3_

- [ ]* 23.3 Write property test for WWW-Authenticate on 401
  - **Property 51: WWW-Authenticate header on 401**
  - **Validates: Requirements 16.1, 16.2, 16.3**

- [ ] 24. Add 406 Not Acceptable response
  - [ ] 24.1 Add Accept header validation
    - Validate Accept header in Request Handler
    - Return 406 if Accept header is not acceptable (not application/json or */*)
    - _Requirements: 5.4_
  - [ ] 24.2 Add unit tests for Accept header validation
    - Test valid Accept headers (application/json, */*, missing)
    - Test invalid Accept headers return 406
    - _Requirements: 5.4_

- [ ]* 24.3 Write property test for unacceptable Accept header rejection
  - **Property 18: Unacceptable Accept header rejection**
  - **Validates: Requirements 5.4**

- [ ] 25. Add new-users-disabled feature
  - [ ] 25.1 Add NEW_USERS_ENABLED configuration
    - Add environment variable (default true)
    - Add to ServiceProvider configuration
    - _Requirements: 17.4_
  - [ ] 25.2 Update UserManager for new users check
    - Add new_users_enabled parameter to constructor
    - Check if user exists before creating
    - Raise NewUsersDisabledError if new users disabled and user doesn't exist
    - _Requirements: 17.1, 17.2_
  - [ ] 25.3 Add unit tests for new users disabled
    - Test new user rejected when disabled
    - Test existing user allowed when disabled
    - Test new user allowed when enabled
    - _Requirements: 17.1, 17.2, 17.3_

- [ ]* 25.4 Write property test for new users disabled
  - **Property 52: New users disabled configuration**
  - **Validates: Requirements 17.1**

- [x] 26. Fix uid generation and database schema for node reset
  - [x] 26.1 Update UserRecord model to remove uid field
    - Remove uid from UserRecord dataclass (it should be derived, not stored)
    - uid is computed on-demand from user_id + generation
    - _Requirements: 2.4, 7.2_
  - [x] 26.2 Update UserManager to use user_id as PK (not uid)
    - Change _user_pk() to accept user_id (OIDC sub) instead of uid
    - Update all methods to use user_id as the stable identifier
    - Update create_user() signature: create_user(user_id: str, client_state: str)
    - Update get_user() signature: get_user(user_id: str)
    - Update get_or_create_user() signature: get_or_create_user(user_id: str, client_state: str)
    - Update increment_generation() signature: increment_generation(user_id: str)
    - Update validate_generation() signature: validate_generation(user_id: str, generation: int)
    - Update update_user_client_state() signature: update_user_client_state(user_id: str, ...)
    - _Requirements: 2.4, 7.1, 7.2_
  - [x] 26.3 Update TokenGenerator.generate_uid() to include generation
    - Change signature: generate_uid(user_id: str, generation: int)
    - uid = hash(user_id + str(generation)) so it changes on node reset
    - _Requirements: 2.4_
  - [x] 26.4 Update RequestTokenRoute flow
    - Extract user_id from OIDC claims (claims.sub)
    - Call user_manager.get_or_create_user(user_id, client_state) FIRST
    - Then derive uid: token_generator.generate_uid(user_id, user_record.generation)
    - Pass uid to generate_token()
    - _Requirements: 2.4_
  - [x] 26.5 Update all UserManager unit tests
    - Update test fixtures to use user_id instead of uid
    - Update all method calls to pass user_id
    - _Requirements: 2.4, 7.1, 7.2_
  - [x] 26.6 Update TokenGenerator unit tests
    - Test generate_uid() with both user_id and generation parameters
    - Test uid changes when generation changes
    - Test same user_id + generation produces same uid
    - _Requirements: 2.4_
  - [x] 26.7 Update RequestTokenRoute unit tests
    - Update test flow to match new order (get_or_create_user before generate_uid)
    - Update mock assertions for user_id instead of uid
    - _Requirements: 2.4_
  - [x] 26.8 Data migration consideration
    - Document that existing DynamoDB records with PK=USER#{uid} need migration
    - Add migration script or manual process to re-key records by user_id
    - Note: This is a breaking change requiring data migration
    - _Requirements: 7.1_

- [ ]* 26.4 Write property test for node reset on client state change
  - **Property 8: Node reset on client state change**
  - **Validates: Requirements 2.4**

- [ ] 27. Checkpoint - Ensure all Mozilla spec compliance tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Phase 3: Integration Tests

- [ ]* 28.1 Write integration test for GET method token issuance
  - Test complete flow using GET method
  - Verify response structure matches Mozilla spec
  - _Requirements: 1.1_

- [ ]* 28.2 Write integration test for client state history
  - Test client state change flow
  - Test rejection of previously-seen client state
  - Test rejection of empty state when history exists
  - _Requirements: 13.6, 13.7, 13.8_

- [ ]* 28.3 Write integration test for new error statuses
  - Test invalid-timestamp response
  - Test invalid-generation response
  - Test invalid-client-state response
  - Test new-users-disabled response
  - _Requirements: 6.6, 6.7, 6.8, 6.9_

- [ ]* 28.4 Write integration test for response headers
  - Test X-Timestamp on 200 and 401
  - Test Retry-After on 503
  - Test WWW-Authenticate on 401
  - _Requirements: 14.1, 14.2, 15.1, 16.1_

- [ ]* 28.5 Write integration test for node reset
  - Test uid changes when client state changes
  - Test api_endpoint changes when client state changes
  - _Requirements: 2.4_

- [ ] 29. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
