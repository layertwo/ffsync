# Requirements Document

## Introduction

This document specifies the requirements for implementing a Firefox Sync Storage Server as a serverless AWS Lambda function. The Storage Server is responsible for storing and retrieving user sync data (bookmarks, tabs, history, passwords, forms, etc.) organized as Basic Storage Objects (BSOs) within named collections. The implementation follows the Mozilla Firefox Sync Storage API 1.5 specification and integrates with AWS services (API Gateway, DynamoDB, Lambda).

## Glossary

- **Storage Server**: The service that stores and retrieves user sync data
- **BSO (Basic Storage Object)**: The fundamental unit of storage containing an ID, payload, modification timestamp, optional sort index, and optional TTL
- **Collection**: A named group of BSOs (e.g., "bookmarks", "tabs", "history", "passwords", "forms")
- **Payload**: The JSON-encoded data content of a BSO, encrypted by the client
- **Modified Timestamp**: Seconds since epoch with 2 decimal places precision (e.g., 1702345678.12)
- **Sort Index**: An integer indicating the relative importance of an item in the collection (max 9 digits)
- **TTL (Time-To-Live)**: Number of seconds until a BSO expires and is automatically deleted (write-only field, not returned in responses)
- **X-Last-Modified**: HTTP header containing the modification timestamp of the target resource
- **X-If-Modified-Since**: HTTP header for conditional GET requests (returns 304 if not modified)
- **X-If-Unmodified-Since**: HTTP header for optimistic concurrency control on write operations
- **X-Weave-Timestamp**: HTTP header containing the current server timestamp
- **X-Weave-Next-Offset**: HTTP header containing an opaque token for pagination
- **X-Weave-Records**: HTTP header indicating total number of records in a response
- **X-Weave-Backoff**: HTTP header indicating server is under heavy load
- **X-Weave-Quota-Remaining**: HTTP header indicating remaining storage quota in KB
- **X-Weave-Alert**: HTTP header for warning messages and service notifications
- **HAWK Authentication**: HTTP authentication scheme using HMAC for request signing
- **Batch Operation**: A single request that creates, updates, or deletes multiple BSOs
- **Batch Upload**: Multi-request batching where multiple POST requests are combined into a single atomic update

## Requirements

### Requirement 1

**User Story:** As a Firefox Sync client, I want to store and retrieve individual BSOs, so that I can sync specific items like bookmarks or passwords.

#### Acceptance Criteria

1. WHEN a client sends a GET request to `/storage/{collection}/{id}`, THE Storage Server SHALL return the BSO with the specified ID including `id`, `payload`, `modified`, and optional `sortindex` fields (TTL is not returned)
2. WHEN a client sends a PUT request to `/storage/{collection}/{id}` with a valid BSO payload, THE Storage Server SHALL create or update the BSO and return the new modification timestamp
3. WHEN a client sends a PUT request with fields not provided in the request body, THE Storage Server SHALL preserve existing field values for updates or use default values for new BSOs
4. WHEN a client sends a PUT request with fields explicitly set to null, THE Storage Server SHALL reset those fields to their default values
5. WHEN a client sends a DELETE request to `/storage/{collection}/{id}`, THE Storage Server SHALL delete the BSO and return the deletion timestamp
6. WHEN a BSO does not exist, THE Storage Server SHALL return a 404 status code
7. WHEN a BSO is retrieved, THE Storage Server SHALL include the `X-Last-Modified` header with the BSO's modification timestamp

### Requirement 2

**User Story:** As a Firefox Sync client, I want to retrieve multiple BSOs from a collection with filtering options, so that I can efficiently sync only the data I need.

#### Acceptance Criteria

1. WHEN a client sends a GET request to `/storage/{collection}`, THE Storage Server SHALL return a JSON array of BSO IDs in the collection
2. WHEN a client sends a GET request to a non-existent collection, THE Storage Server SHALL return an empty list (not 404)
3. WHEN a client sends a GET request with `full=true`, THE Storage Server SHALL return a JSON array of complete BSO objects instead of just IDs
4. WHEN a client sends a GET request with `ids={id1},{id2},...`, THE Storage Server SHALL return only BSOs with the specified IDs (comma-separated, max 100 IDs)
5. WHEN a client sends a GET request with more than 100 IDs, THE Storage Server SHALL return a 400 status code
6. WHEN a client sends a GET request with `newer={timestamp}`, THE Storage Server SHALL return only BSOs modified strictly after the specified timestamp
7. WHEN a client sends a GET request with `older={timestamp}`, THE Storage Server SHALL return only BSOs modified strictly before the specified timestamp
8. WHEN a client sends a GET request with `sort=newest`, THE Storage Server SHALL return BSOs sorted by modification timestamp in descending order
9. WHEN a client sends a GET request with `sort=oldest`, THE Storage Server SHALL return BSOs sorted by modification timestamp in ascending order
10. WHEN a client sends a GET request with `sort=index`, THE Storage Server SHALL return BSOs sorted by sortindex in descending order (highest weight first)
11. WHEN a client sends a GET request with `limit={n}`, THE Storage Server SHALL return at most n BSOs
12. WHEN a client sends a GET request with `offset={token}`, THE Storage Server SHALL skip items using the opaque token from a previous X-Weave-Next-Offset header
13. WHEN more results are available beyond the limit, THE Storage Server SHALL include an `X-Weave-Next-Offset` header with an opaque token for the next page
14. WHEN returning multiple records, THE Storage Server MAY include an `X-Weave-Records` header indicating the total number of records in the response

### Requirement 3

**User Story:** As a Firefox Sync client, I want to perform batch operations on BSOs, so that I can efficiently sync multiple items in a single request.

#### Acceptance Criteria

1. WHEN a client sends a POST request to `/storage/{collection}` with a JSON array of BSOs, THE Storage Server SHALL create or update each BSO in the batch
2. WHEN a batch operation completes, THE Storage Server SHALL return a JSON object with `modified` timestamp, `success` array of successfully processed IDs, and `failed` object mapping failed IDs to error strings
3. WHEN a BSO in a batch fails validation, THE Storage Server SHALL continue processing other BSOs and report the failure in the `failed` object
4. WHEN a batch request exceeds the `max_post_records` limit, THE Storage Server SHALL return a 400 status code with response code 17
5. WHEN a batch request exceeds the `max_post_bytes` limit, THE Storage Server SHALL return a 400 status code with response code 17
6. WHEN a batch request exceeds the `max_request_bytes` limit, THE Storage Server SHALL return a 413 status code
7. WHEN a client includes `X-Weave-Records` header with POST request, THE Storage Server SHALL validate the record count before processing
8. WHEN a client includes `X-Weave-Bytes` header with POST request, THE Storage Server SHALL validate the payload size before processing

### Requirement 4

**User Story:** As a Firefox Sync client, I want to delete multiple BSOs at once, so that I can efficiently remove synced data.

#### Acceptance Criteria

1. WHEN a client sends a DELETE request to `/storage/{collection}` with `ids={id1},{id2},...`, THE Storage Server SHALL delete only the specified BSOs and return a JSON object with `modified` timestamp
2. WHEN a client sends a DELETE request with more than 100 IDs, THE Storage Server SHALL return a 400 status code
3. WHEN a client sends a DELETE request to `/storage/{collection}` without IDs, THE Storage Server SHALL delete the entire collection
4. WHEN a collection is deleted, THE Storage Server SHALL remove it from `/info/collections` output
5. WHEN BSOs are deleted from a collection (with IDs), THE Storage Server SHALL update the collection's last-modified time and keep it in `/info/collections`
6. WHEN a client sends a DELETE request to `/storage`, THE Storage Server SHALL delete all collections and BSOs for the user
7. WHEN a client sends a DELETE request to the root endpoint `/`, THE Storage Server SHALL delete all collections and BSOs for the user
8. WHEN a delete operation completes, THE Storage Server SHALL return the deletion timestamp

### Requirement 5

**User Story:** As a Firefox Sync client, I want to use optimistic concurrency control, so that I can detect and handle concurrent modifications.

#### Acceptance Criteria

1. WHEN a client sends a write request with `X-If-Unmodified-Since` header, THE Storage Server SHALL compare the header value against the target resource's last modification timestamp
2. WHEN the resource has been modified since the `X-If-Unmodified-Since` timestamp, THE Storage Server SHALL return a 412 Precondition Failed status code
3. WHEN a client sends `X-If-Unmodified-Since: 0`, THE Storage Server SHALL treat this as "create only if not exists" and return 412 if the resource exists
4. WHEN a write operation succeeds, THE Storage Server SHALL return the new modification timestamp in the `X-Last-Modified` header
5. WHEN a read operation succeeds, THE Storage Server SHALL return the resource's last modification timestamp in the `X-Last-Modified` header
6. WHEN concurrent write requests conflict, THE Storage Server SHALL return a 409 Conflict status code
7. WHEN a 409 Conflict is returned, THE Storage Server MAY include a `Retry-After` header indicating when to retry

### Requirement 6

**User Story:** As a Firefox Sync client, I want to use conditional GET requests, so that I can avoid re-downloading unchanged data.

#### Acceptance Criteria

1. WHEN a client sends a GET request with `X-If-Modified-Since` header, THE Storage Server SHALL compare the header value against the target resource's last modification timestamp
2. WHEN the resource has not been modified since the `X-If-Modified-Since` timestamp, THE Storage Server SHALL return a 304 Not Modified status code
3. WHEN both `X-If-Modified-Since` and `X-If-Unmodified-Since` headers are present, THE Storage Server SHALL return a 400 Bad Request status code
4. WHEN the `X-If-Modified-Since` header value is not a valid positive decimal, THE Storage Server SHALL return a 400 Bad Request status code

### Requirement 7

**User Story:** As a Firefox Sync client, I want to query collection metadata, so that I can determine what data needs to be synced.

#### Acceptance Criteria

1. WHEN a client sends a GET request to `/info/collections`, THE Storage Server SHALL return a JSON object mapping collection names to their last modification timestamps
2. WHEN a client sends a GET request to `/info/collection_counts`, THE Storage Server SHALL return a JSON object mapping collection names to the number of BSOs they contain
3. WHEN a client sends a GET request to `/info/collection_usage`, THE Storage Server SHALL return a JSON object mapping collection names to their storage usage in KB
4. WHEN a client sends a GET request to `/info/quota`, THE Storage Server SHALL return a two-item list with current usage and quota in KB (quota is null if not enforced)

### Requirement 8

**User Story:** As a Firefox Sync client, I want to know the server's configuration limits, so that I can respect them when syncing data.

#### Acceptance Criteria

1. WHEN a client sends a GET request to `/info/configuration`, THE Storage Server SHALL return a JSON object with server limits
2. WHEN the configuration is returned, THE response SHALL include `max_request_bytes` indicating the maximum request body size in bytes
3. WHEN the configuration is returned, THE response SHALL include `max_post_records` indicating the maximum number of BSOs per POST request
4. WHEN the configuration is returned, THE response SHALL include `max_post_bytes` indicating the maximum combined payload size for POST requests in bytes
5. WHEN the configuration is returned, THE response SHALL include `max_total_records` indicating the maximum BSOs in a batched upload (optional, may be omitted if unlimited)
6. WHEN the configuration is returned, THE response SHALL include `max_total_bytes` indicating the maximum combined payload size for batched uploads in bytes (optional, may be omitted if unlimited)
7. WHEN the configuration is returned, THE response SHALL include `max_record_payload_bytes` indicating the maximum individual BSO payload size in bytes

### Requirement 9

**User Story:** As a Firefox Sync client, I want all responses to include the current server timestamp, so that I can synchronize my local clock.

#### Acceptance Criteria

1. WHEN the Storage Server returns any response, THE response SHALL include the `X-Weave-Timestamp` header with the current server time
2. WHEN the `X-Weave-Timestamp` header is generated, THE value SHALL be seconds since epoch with 2 decimal places precision
3. WHEN responding to a write request, THE `X-Weave-Timestamp` value SHALL equal the `X-Last-Modified` value
4. WHEN responding to a read request, THE `X-Weave-Timestamp` value SHALL be greater than or equal to the `X-Last-Modified` value

### Requirement 10

**User Story:** As a Firefox Sync client, I want BSO payloads to be validated, so that invalid data is rejected.

#### Acceptance Criteria

1. WHEN a BSO payload exceeds `max_record_payload_bytes`, THE Storage Server SHALL return a 413 status code
2. WHEN a BSO ID exceeds 64 characters, THE Storage Server SHALL return a 400 status code
3. WHEN a BSO ID contains characters other than printable ASCII (0x20-0x7E), THE Storage Server SHALL return a 400 status code
4. WHEN a BSO sortindex is not an integer or exceeds 9 digits, THE Storage Server SHALL return a 400 status code
5. WHEN a BSO TTL is not a positive integer or exceeds 9 digits, THE Storage Server SHALL return a 400 status code

### Requirement 11

**User Story:** As a Firefox Sync client, I want expired BSOs to be automatically removed, so that storage is efficiently managed.

#### Acceptance Criteria

1. WHEN a BSO has a TTL set, THE Storage Server SHALL automatically delete the BSO after the TTL expires
2. WHEN a BSO is updated with a new TTL, THE Storage Server SHALL reset the expiration time based on the new TTL
3. WHEN a BSO is retrieved after its TTL has expired, THE Storage Server SHALL return a 404 status code
4. WHEN a BSO is returned in a response, THE Storage Server SHALL NOT include the TTL field (TTL is write-only)

### Requirement 12

**User Story:** As a system operator, I want the Storage Server to authenticate requests using HAWK, so that only authorized users can access their data.

#### Acceptance Criteria

1. WHEN a client sends a request without HAWK authentication, THE Storage Server SHALL return a 401 status code
2. WHEN a client sends a request with invalid HAWK credentials, THE Storage Server SHALL return a 401 status code
3. WHEN a client sends a request with expired HAWK credentials, THE Storage Server SHALL return a 401 status code
4. WHEN HAWK authentication succeeds, THE Storage Server SHALL extract the user ID from the HAWK credentials
5. WHEN a user accesses storage, THE Storage Server SHALL ensure the user can only access their own data

### Requirement 13

**User Story:** As a system operator, I want the Storage Server to return consistent error responses, so that clients can handle errors appropriately.

#### Acceptance Criteria

1. WHEN the Storage Server returns an error with Content-Type application/json, THE response body SHALL be an integer response code
2. WHEN a JSON parse failure occurs, THE Storage Server SHALL return response code 6
3. WHEN an invalid BSO is submitted, THE Storage Server SHALL return response code 8
4. WHEN an invalid collection name is used, THE Storage Server SHALL return response code 13
5. WHEN a user exceeds their storage quota, THE Storage Server SHALL return a 400 status code with response code 14
6. WHEN a client is known to be incompatible, THE Storage Server SHALL return response code 16
7. WHEN server limits are exceeded, THE Storage Server SHALL return response code 17
8. WHEN a server error occurs, THE Storage Server SHALL return a 500 status code with a generic error message

### Requirement 14

**User Story:** As a system operator, I want the Storage Server to log operations, so that issues can be diagnosed and usage can be monitored.

#### Acceptance Criteria

1. WHEN a request is processed, THE Storage Server SHALL log the request method, path, and user ID
2. WHEN an error occurs, THE Storage Server SHALL log the error details and stack trace
3. WHEN the Storage Server logs events, THE Storage Server SHALL use structured logging with JSON format
4. WHEN the Storage Server logs events, THE Storage Server SHALL NOT log BSO payloads or other sensitive user data

### Requirement 15

**User Story:** As a Firefox Sync client, I want collection names to be validated, so that only valid collections can be created.

#### Acceptance Criteria

1. WHEN a collection name exceeds 32 characters, THE Storage Server SHALL return a 400 status code with response code 13
2. WHEN a collection name contains characters other than urlsafe-base64 alphabet (alphanumeric, underscore, hyphen) and period, THE Storage Server SHALL return a 400 status code with response code 13
3. WHEN a collection name is valid, THE Storage Server SHALL accept alphanumeric characters (a-z, A-Z, 0-9), underscores, hyphens, and periods

### Requirement 16

**User Story:** As a Firefox Sync client, I want to receive appropriate HTTP status codes, so that I can handle different scenarios correctly.

#### Acceptance Criteria

1. WHEN a GET request succeeds, THE Storage Server SHALL return a 200 status code
2. WHEN a PUT request creates or updates a BSO, THE Storage Server SHALL return a 200 status code with the modification timestamp
3. WHEN a POST batch operation succeeds, THE Storage Server SHALL return a 200 status code with the batch result
4. WHEN a DELETE request succeeds, THE Storage Server SHALL return a 200 status code with the deletion timestamp
5. WHEN a resource has not been modified (X-If-Modified-Since), THE Storage Server SHALL return a 304 status code
6. WHEN a request is malformed, THE Storage Server SHALL return a 400 status code
7. WHEN authentication fails, THE Storage Server SHALL return a 401 status code
8. WHEN a BSO resource is not found, THE Storage Server SHALL return a 404 status code
9. WHEN a request method is not supported for a URL, THE Storage Server SHALL return a 405 status code
10. WHEN concurrent writes conflict, THE Storage Server SHALL return a 409 status code
11. WHEN a precondition fails (X-If-Unmodified-Since), THE Storage Server SHALL return a 412 status code
12. WHEN a request body is too large, THE Storage Server SHALL return a 413 status code
13. WHEN Content-Type is not supported, THE Storage Server SHALL return a 415 status code
14. WHEN the server is under maintenance, THE Storage Server SHALL return a 503 status code with Retry-After header

### Requirement 17

**User Story:** As a Firefox Sync client, I want to use different content types for requests and responses, so that I can optimize data transfer.

#### Acceptance Criteria

1. WHEN a client sends a POST request with Content-Type application/json, THE Storage Server SHALL parse the body as a JSON array of BSOs
2. WHEN a client sends a POST request with Content-Type application/newlines, THE Storage Server SHALL parse each line as a separate JSON BSO
3. WHEN a client sends a POST request with Content-Type text/plain, THE Storage Server SHALL treat it as application/json for backwards compatibility
4. WHEN a client sends a GET request with Accept application/json, THE Storage Server SHALL return a JSON array
5. WHEN a client sends a GET request with Accept application/newlines, THE Storage Server SHALL return each record on a separate line

### Requirement 18

**User Story:** As a Firefox Sync client, I want to receive server status information, so that I can handle service degradation gracefully.

#### Acceptance Criteria

1. WHEN the server is under heavy load, THE Storage Server MAY include an `X-Weave-Backoff` header with the number of seconds to wait before making additional requests
2. WHEN a write request succeeds and quotas are enabled, THE Storage Server MAY include an `X-Weave-Quota-Remaining` header with remaining storage in KB
3. WHEN the server has important notifications, THE Storage Server MAY include an `X-Weave-Alert` header with a message or JSON object
4. WHEN the service is being decommissioned, THE Storage Server SHALL return a 513 status code with X-Weave-Alert containing code "hard-eol"

