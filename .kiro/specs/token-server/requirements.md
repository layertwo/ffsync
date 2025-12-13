# Requirements Document

## Introduction

This document specifies the requirements for implementing a Firefox Sync Token Server as a serverless AWS Lambda function. The Token Server is responsible for authenticating users, issuing time-limited authentication tokens, and providing node assignment information that directs clients to the appropriate storage endpoint. The implementation will integrate with AWS services (API Gateway, DynamoDB, Lambda) and follow the Mozilla Token Server API v1.0 specification.

## Glossary

- **Token Server**: The authentication service that issues bearer tokens to authenticated clients
- **Bearer Token**: A time-limited authentication credential used to access the Storage API
- **Node Assignment**: The storage endpoint URL assigned to a user for accessing their sync data
- **BrowserID Assertion**: A cryptographic assertion proving user identity (legacy authentication method)
- **OAuth Token**: An OAuth 2.0 access token used for modern authentication
- **OIDC Provider**: An OpenID Connect identity provider (e.g., Authentik, Authelia, Pocket ID) that issues OAuth tokens
- **OIDC Token**: An access token or ID token issued by an OIDC provider
- **JWKS Endpoint**: JSON Web Key Set endpoint used to retrieve public keys for token verification
- **Token Introspection**: The process of validating an OAuth token with the issuing OIDC provider
- **Token Endpoint**: The API endpoint that exchanges authentication credentials for bearer tokens
- **Storage Endpoint**: The base URL where a user's sync data is stored
- **Token Duration**: The validity period of an issued bearer token (typically 300 seconds)
- **User Identifier**: A unique identifier for a user derived from their authentication credentials
- **Generation Number**: A monotonically increasing counter used to invalidate old tokens
- **HAWK Authentication**: HTTP authentication scheme using HMAC for request signing
- **Client State History**: A server-side list of previously-seen X-Client-State values for each user
- **Urlsafe-Base64 Alphabet**: Characters allowed in URL-safe base64 encoding: alphanumeric (a-z, A-Z, 0-9), underscore (_), hyphen (-), and period (.)

## Requirements

### Requirement 1

**User Story:** As a Firefox Sync client, I want to exchange my authentication credentials for a bearer token, so that I can access the Storage API.

#### Acceptance Criteria

1. WHEN a client sends a GET request to `/1.0/sync/1.5` with valid OIDC credentials in the Authorization header, THE Token Server SHALL return a JSON response containing id, key, uid, api_endpoint, and duration fields
2. WHEN a client sends a request with an OIDC token in the Authorization header using Bearer scheme, THE Token Server SHALL validate the token with the configured OIDC provider
3. WHEN a client sends a request with invalid credentials, THE Token Server SHALL return a 401 status code with an error message
4. WHEN a client sends a request with a malformed Authorization header, THE Token Server SHALL return a 400 status code with a validation error
5. WHEN the Token Server issues a bearer token, THE bearer token SHALL be valid for 300 seconds

### Requirement 2

**User Story:** As a Firefox Sync client, I want to receive consistent node assignment, so that I can reliably access my sync data at the same endpoint.

#### Acceptance Criteria

1. WHEN a user requests a token, THE Token Server SHALL compute the storage node URL dynamically based on the user identifier
2. WHEN a user requests a token multiple times, THE Token Server SHALL return the same node assignment for the same user identifier
3. WHEN the Token Server computes a node URL, THE node URL SHALL follow the format `https://{base_url}/1.5/{uid}`
4. WHEN a user's X-Client-State changes, THE Token Server SHALL reset the node allocation by generating a new uid and api_endpoint
5. WHEN the Token Server returns a token response, THE response SHALL include the `api_endpoint` field containing the full storage URL

### Requirement 3

**User Story:** As a system administrator, I want user tokens to be invalidated when security events occur, so that compromised accounts can be protected.

#### Acceptance Criteria

1. WHEN a user's generation number is incremented, THE Token Server SHALL invalidate all previously issued tokens for that user
2. WHEN the Token Server validates a bearer token, THE Token Server SHALL verify the token's generation number matches the current user generation
3. WHEN a bearer token has an outdated generation number, THE Token Server SHALL reject the token with a 401 status code and "invalid-generation" status
4. WHEN the Token Server stores user data, THE Token Server SHALL include a generation number field with a default value of 0
5. WHEN a generation number is updated, THE Token Server SHALL ensure the new value is greater than the previous value
6. WHEN a client's X-Client-State changes from a previously stored value, THE Token Server SHALL increment the generation number
7. WHEN an administrator triggers a password reset or key rotation event, THE Token Server SHALL increment the affected user's generation number

### Requirement 4

**User Story:** As a Firefox Sync client, I want to use HAWK authentication with my bearer token, so that my Storage API requests are cryptographically signed.

#### Acceptance Criteria

1. WHEN the Token Server issues a bearer token, THE response SHALL include an `id` field containing the HAWK identifier
2. WHEN the Token Server issues a bearer token, THE response SHALL include a `key` field containing the HAWK shared secret
3. WHEN the Token Server generates HAWK credentials, THE `id` SHALL be a URL-safe base64-encoded string
4. WHEN the Token Server generates HAWK credentials, THE `key` SHALL be a cryptographically random 32-byte value encoded as hexadecimal
5. WHEN a client uses HAWK authentication, THE Storage API SHALL validate the HAWK signature using the shared secret

### Requirement 5

**User Story:** As a system operator, I want the Token Server to validate request parameters, so that malformed requests are rejected early.

#### Acceptance Criteria

1. WHEN a client sends a request without an Authorization header, THE Token Server SHALL return a 401 status code
2. WHEN a client sends a request to an invalid endpoint path, THE Token Server SHALL return a 404 status code
3. WHEN a client sends a request with an unsupported HTTP method, THE Token Server SHALL return a 405 status code
4. WHEN a client sends a request with an unacceptable Accept header, THE Token Server SHALL return a 406 status code
5. WHEN the Token Server encounters a validation error, THE response SHALL include a descriptive error message

### Requirement 6

**User Story:** As a Firefox Sync client, I want to receive error responses in a consistent format, so that I can handle errors appropriately.

#### Acceptance Criteria

1. WHEN the Token Server returns an error response, THE response SHALL be valid JSON with Content-Type application/json
2. WHEN the Token Server returns an error response, THE JSON SHALL contain a `status` field with the error type
3. WHEN the Token Server returns an error response, THE JSON SHALL contain an `errors` array with error details
4. WHEN a 401 error occurs due to invalid credentials, THE `status` field SHALL contain "invalid-credentials"
5. WHEN a validation error occurs, THE `errors` array SHALL contain objects with `location`, `name`, and `description` fields
6. WHEN a 401 error occurs due to timestamp skew, THE `status` field SHALL contain "invalid-timestamp"
7. WHEN a 401 error occurs due to outdated generation, THE `status` field SHALL contain "invalid-generation"
8. WHEN a 401 error occurs due to invalid client state transition, THE `status` field SHALL contain "invalid-client-state"
9. WHEN a 401 error occurs because new users are disabled, THE `status` field SHALL contain "new-users-disabled"

### Requirement 7

**User Story:** As a system administrator, I want user authentication data stored securely in DynamoDB, so that token validation is fast and scalable.

#### Acceptance Criteria

1. WHEN the Token Server creates a user record, THE Token Server SHALL store the record in a DynamoDB table with a partition key of `user_id`
2. WHEN the Token Server stores user data, THE Token Server SHALL include fields for `user_id`, `generation`, `client_state`, `client_state_history`, `created_at`, and `updated_at`
3. WHEN the Token Server queries user data, THE Token Server SHALL use the `user_id` as the partition key for efficient lookups
4. WHEN a user record does not exist, THE Token Server SHALL create a new record with generation 0 and empty client_state
5. WHEN the Token Server updates a user record, THE Token Server SHALL update the `updated_at` timestamp
6. WHEN the Token Server stores client_state_history, THE Token Server SHALL maintain a list of all previously-seen X-Client-State values for the user

### Requirement 8

**User Story:** As a Firefox Sync client, I want the Token Server to support CORS, so that web-based clients can authenticate.

#### Acceptance Criteria

1. WHEN a client sends an OPTIONS request, THE Token Server SHALL return appropriate CORS headers
2. WHEN the Token Server returns a response, THE Token Server SHALL include the `Access-Control-Allow-Origin` header
3. WHEN the Token Server returns a response, THE Token Server SHALL include the `Access-Control-Allow-Methods` header with supported methods
4. WHEN the Token Server returns a response, THE Token Server SHALL include the `Access-Control-Allow-Headers` header
5. WHEN a preflight request is received, THE Token Server SHALL return a 200 status code with CORS headers

### Requirement 9

**User Story:** As a system administrator, I want the Token Server to integrate with external OIDC providers, so that users can authenticate using their existing identity provider.

#### Acceptance Criteria

1. WHEN the Token Server is configured, THE Token Server SHALL accept an OIDC provider URL as a configuration parameter
2. WHEN the Token Server starts, THE Token Server SHALL discover the OIDC provider's configuration from the `.well-known/openid-configuration` endpoint
3. WHEN the Token Server validates an OIDC token, THE Token Server SHALL verify the token signature using the provider's JWKS endpoint
4. WHEN the Token Server validates an OIDC token, THE Token Server SHALL verify the token issuer matches the configured OIDC provider
5. WHEN the Token Server validates an OIDC token, THE Token Server SHALL verify the token audience matches the expected client ID

### Requirement 10

**User Story:** As a system administrator, I want to configure the Token Server with OIDC provider details, so that it can validate tokens from my chosen identity provider.

#### Acceptance Criteria

1. WHEN the Token Server is deployed, THE Token Server SHALL read the OIDC provider URL from an environment variable
2. WHEN the Token Server is deployed, THE Token Server SHALL read the expected client ID from an environment variable
3. WHEN the OIDC provider URL is not configured, THE Token Server SHALL fail to start with a clear error message
4. WHEN the Token Server caches OIDC provider configuration, THE Token Server SHALL refresh the cache periodically
5. WHEN the Token Server cannot reach the OIDC provider, THE Token Server SHALL return a 503 status code with a service unavailable error

### Requirement 11

**User Story:** As a developer, I want the Token Server to extract user identity from OIDC tokens, so that users are properly identified.

#### Acceptance Criteria

1. WHEN the Token Server receives an OIDC token, THE Token Server SHALL extract the user identifier from the `sub` claim
2. WHEN the Token Server validates an OIDC token, THE Token Server SHALL verify the token has not expired by checking the `exp` claim
3. WHEN an OIDC token is expired, THE Token Server SHALL return a 401 status code with an "invalid-credentials" error
4. WHEN the Token Server cannot extract a user identifier, THE Token Server SHALL return a 401 status code
5. WHEN the Token Server extracts a user identifier, THE Token Server SHALL use the identifier consistently for node assignment and token generation

### Requirement 12

**User Story:** As a system operator, I want the Token Server to log authentication events, so that security issues can be investigated.

#### Acceptance Criteria

1. WHEN a token is successfully issued, THE Token Server SHALL log the user identifier and timestamp
2. WHEN authentication fails, THE Token Server SHALL log the failure reason and timestamp
3. WHEN a validation error occurs, THE Token Server SHALL log the error details
4. WHEN the Token Server logs events, THE Token Server SHALL use structured logging with JSON format
5. WHEN the Token Server logs events, THE Token Server SHALL NOT log sensitive data such as bearer tokens or HAWK keys

### Requirement 13

**User Story:** As a Firefox Sync client, I want the Token Server to track my encryption key state, so that key rotation scenarios are handled correctly.

#### Acceptance Criteria

1. WHEN a client sends a request with an X-Client-State header, THE Token Server SHALL store the client state value with the user record
2. WHEN a client sends a request with a different X-Client-State than previously stored, THE Token Server SHALL increment the user's generation number and reset node allocation
3. WHEN a client sends a request without an X-Client-State header, THE Token Server SHALL accept the request and use an empty string as the default value
4. WHEN the Token Server validates X-Client-State, THE value SHALL contain only characters from the urlsafe-base64 alphabet (alphanumeric, underscore, hyphen) and period, up to 32 characters
5. WHEN a client sends an invalid X-Client-State format, THE Token Server SHALL return a 400 status code with a validation error
6. WHEN a client sends an X-Client-State that matches a previously-seen value in the user's history, THE Token Server SHALL return a 401 status code with "invalid-client-state" status
7. WHEN a client sends an empty X-Client-State but the server has previously seen a non-empty value, THE Token Server SHALL return a 401 status code with "invalid-client-state" status
8. WHEN the Token Server accepts a new X-Client-State, THE Token Server SHALL add the previous value to the client_state_history list

### Requirement 14

**User Story:** As a Firefox Sync client, I want the Token Server to include timestamp information in responses, so that I can detect clock skew for HAWK authentication.

#### Acceptance Criteria

1. WHEN the Token Server returns a 200 successful response, THE response SHALL include an X-Timestamp header with the current server time in seconds since epoch
2. WHEN the Token Server returns a 401 error response, THE response SHALL include an X-Timestamp header with the current server time
3. WHEN the X-Timestamp header is generated, THE value SHALL be an integer representing Unix epoch seconds (POSIX timestamp)

### Requirement 15

**User Story:** As a Firefox Sync client, I want the Token Server to communicate server load and maintenance status, so that I can adjust my request behavior appropriately.

#### Acceptance Criteria

1. WHEN the Token Server returns a 503 status code, THE response SHALL include a Retry-After header with the number of seconds to wait before retrying
2. WHEN the Token Server is under heavy load but still operational, THE response MAY include an X-Backoff header with the number of seconds to avoid unnecessary requests
3. WHEN an X-Backoff header is included, THE header MAY be included with any response type including 200 OK
4. WHEN a client receives a Retry-After header, THE client SHALL NOT attempt further requests until the specified time has elapsed
5. WHEN a client receives an X-Backoff header, THE client SHOULD avoid pre-emptively refreshing tokens for the specified duration

### Requirement 16

**User Story:** As a Firefox Sync client, I want the Token Server to provide authentication challenge information, so that I can understand supported authentication schemes.

#### Acceptance Criteria

1. WHEN the Token Server returns a 401 status code, THE response SHALL include one or more WWW-Authenticate headers
2. WHEN the Token Server includes WWW-Authenticate headers, THE headers SHALL indicate supported authentication schemes
3. WHEN Bearer authentication is supported, THE WWW-Authenticate header SHALL include "Bearer" scheme

### Requirement 17

**User Story:** As a system administrator, I want to control whether new users can register, so that I can manage server capacity.

#### Acceptance Criteria

1. WHEN new user registration is disabled in configuration, THE Token Server SHALL reject requests from unknown users
2. WHEN a new user is rejected due to disabled registration, THE Token Server SHALL return a 401 status code with "new-users-disabled" status
3. WHEN new user registration is enabled, THE Token Server SHALL create records for previously unseen users
4. WHEN the Token Server is deployed, THE Token Server SHALL read the new users enabled setting from configuration

### Requirement 18

**User Story:** As a Firefox Sync client, I want the Token Server to validate timestamp in my authentication, so that replay attacks are prevented.

#### Acceptance Criteria

1. WHEN the Token Server validates an OIDC token, THE Token Server SHALL check the token's issued-at (iat) claim
2. WHEN the token's timestamp differs significantly from server time, THE Token Server SHALL return a 401 status code with "invalid-timestamp" status
3. WHEN timestamp validation fails, THE response SHALL include X-Timestamp header to help client adjust clock
4. WHEN the Token Server validates timestamps, THE Token Server SHALL allow a reasonable clock skew tolerance (configurable, default 5 minutes)
