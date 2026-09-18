from http import HTTPStatus
from typing import Optional

from aws_lambda_powertools.event_handler import Response

# Mozilla Firefox Sync response codes
# These are returned in the response body for certain error conditions
CODE_JSON_PARSE_FAILURE = 6
CODE_INVALID_BSO = 8
CODE_INVALID_COLLECTION = 13
CODE_QUOTA_EXCEEDED = 14
CODE_INCOMPATIBLE_CLIENT = 16
CODE_SERVER_LIMIT_EXCEEDED = 17


class SyncStorageException(Exception):
    """Base exception for SyncStorage API"""

    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code = "InternalServerError"
    mozilla_code: Optional[int] = None  # Mozilla response code (integer) for specific errors
    default_message = "Internal server error"  # Subclasses override; used when message is omitted

    def __init__(
        self,
        message: Optional[str] = None,
        retry_after: Optional[int] = None,
        backoff: Optional[int] = None,
        alert: Optional[str] = None,
    ):
        self.message = message if message is not None else self.default_message
        self.retry_after = retry_after  # Retry-After header (seconds)
        self.backoff = backoff  # X-Weave-Backoff header (seconds)
        self.alert = alert  # X-Weave-Alert header (message or JSON)
        super().__init__(self.message)

    def to_response(self) -> Response:
        """
        Convert exception to HTTP response.

        Per Mozilla spec (Requirement 13.1):
        - If mozilla_code is set, return just the integer code
        - Otherwise, return error object with error_code and message

        Optional headers (Requirements 5.7, 18.1-18.4):
        - Retry-After: Seconds to wait before retrying (for 409, 503)
        - X-Weave-Backoff: Seconds to wait before making additional requests (server load)
        - X-Weave-Alert: Warning message or JSON object
        """
        if self.mozilla_code is not None:
            # Return integer response code per Mozilla spec
            body = str(self.mozilla_code)
        else:
            # Return error object for other errors
            body = f'{{"error": "{self.error_code}", "message": "{self.message}"}}'

        # Build optional headers
        headers = {}
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        if self.backoff is not None:
            headers["X-Weave-Backoff"] = str(self.backoff)
        if self.alert is not None:
            headers["X-Weave-Alert"] = self.alert

        return Response(
            status_code=self.status_code,
            content_type="application/json",
            body=body,
            headers=headers if headers else None,
        )


class ValidationException(SyncStorageException):
    """Validation error exception"""

    status_code = HTTPStatus.BAD_REQUEST
    error_code = "ValidationException"
    default_message = "Invalid request parameters"


class ConflictException(SyncStorageException):
    """Conflict error exception"""

    status_code = HTTPStatus.CONFLICT
    error_code = "ConflictException"
    default_message = "Resource conflict"


class PreconditionFailedException(SyncStorageException):
    """Precondition failed exception"""

    status_code = HTTPStatus.PRECONDITION_FAILED
    error_code = "PreconditionFailedException"
    default_message = "Precondition failed"


class QuotaExceededException(SyncStorageException):
    """Quota exceeded exception (Mozilla response code 14)"""

    status_code = HTTPStatus.INSUFFICIENT_STORAGE
    error_code = "QuotaExceededException"
    mozilla_code = CODE_QUOTA_EXCEEDED
    default_message = "Storage quota exceeded"


class CollectionNotFoundException(SyncStorageException):
    """Collection not found exception"""

    status_code = HTTPStatus.NOT_FOUND
    error_code = "CollectionNotFoundException"
    default_message = "Collection not found"


class StorageObjectNotFoundException(SyncStorageException):
    """Storage object not found exception"""

    status_code = HTTPStatus.NOT_FOUND
    error_code = "StorageObjectNotFoundException"
    default_message = "Storage object not found"


class AuthenticationException(SyncStorageException):
    """Authentication error exception"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "AuthenticationException"
    default_message = "Authentication required"


class RequestTooLargeException(SyncStorageException):
    """Request entity too large exception"""

    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    error_code = "RequestTooLargeException"
    default_message = "Request entity too large"


class MethodNotAllowedException(SyncStorageException):
    """Method not allowed exception"""

    status_code = HTTPStatus.METHOD_NOT_ALLOWED
    error_code = "MethodNotAllowedException"
    default_message = "Method not allowed"


class UnsupportedMediaTypeException(SyncStorageException):
    """Unsupported media type exception"""

    status_code = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    error_code = "UnsupportedMediaTypeException"
    default_message = "Unsupported media type"


class ServerLimitExceededException(SyncStorageException):
    """Server limit exceeded exception (Mozilla response code 17)"""

    status_code = HTTPStatus.BAD_REQUEST
    error_code = "ServerLimitExceededException"
    mozilla_code = CODE_SERVER_LIMIT_EXCEEDED
    default_message = "Server limit exceeded"


class InvalidBSOException(SyncStorageException):
    """Invalid BSO exception (Mozilla response code 8)"""

    status_code = HTTPStatus.BAD_REQUEST
    error_code = "InvalidBSOException"
    mozilla_code = CODE_INVALID_BSO
    default_message = "Invalid BSO"


class InvalidCollectionException(SyncStorageException):
    """Invalid collection name exception (Mozilla response code 13)"""

    status_code = HTTPStatus.BAD_REQUEST
    error_code = "InvalidCollectionException"
    mozilla_code = CODE_INVALID_COLLECTION
    default_message = "Invalid collection name"


class JSONParseException(SyncStorageException):
    """JSON parse failure exception (Mozilla response code 6)"""

    status_code = HTTPStatus.BAD_REQUEST
    error_code = "JSONParseException"
    mozilla_code = CODE_JSON_PARSE_FAILURE
    default_message = "JSON parse failure"


class IncompatibleClientException(SyncStorageException):
    """Incompatible client exception (Mozilla response code 16)"""

    status_code = HTTPStatus.BAD_REQUEST
    error_code = "IncompatibleClientException"
    mozilla_code = CODE_INCOMPATIBLE_CLIENT
    default_message = "Incompatible client"


# Token Server specific exceptions


class InvalidTokenError(SyncStorageException):
    """Raised when an OIDC token is invalid or cannot be validated"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "InvalidTokenError"
    default_message = "Invalid or expired token"


class InvalidCredentialsError(SyncStorageException):
    """Raised when authentication credentials are invalid"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "InvalidCredentialsError"
    default_message = "Invalid credentials"


class TokenValidationError(ValidationException):
    """Raised when token validation fails"""

    default_message = "Token validation failed"


class ServiceUnavailableError(SyncStorageException):
    """Raised when external services (OIDC provider, DynamoDB) are unavailable"""

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    error_code = "ServiceUnavailableError"
    default_message = "Service temporarily unavailable"


class InvalidTimestampError(SyncStorageException):
    """Raised when OIDC token timestamp differs significantly from server time"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "InvalidTimestampError"
    status_field = "invalid-timestamp"
    default_message = "Token timestamp differs significantly from server time"


class InvalidGenerationError(SyncStorageException):
    """Raised when bearer token has an outdated generation number"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "InvalidGenerationError"
    status_field = "invalid-generation"
    default_message = "Token generation number is outdated"


class InvalidClientStateError(SyncStorageException):
    """Raised when client state transition is invalid (e.g., previously-seen state)"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "InvalidClientStateError"
    status_field = "invalid-client-state"
    default_message = "Invalid client state transition"


class NewUsersDisabledError(SyncStorageException):
    """Raised when new user registration is disabled and user doesn't exist"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "NewUsersDisabledError"
    status_field = "new-users-disabled"
    default_message = "New user registration is disabled"


# HAWK Authentication specific exceptions


class InvalidHawkHeaderException(AuthenticationException):
    """Raised when HAWK Authorization header is malformed"""

    default_message = "Malformed HAWK Authorization header"


class InvalidHawkSignatureException(AuthenticationException):
    """Raised when HAWK signature verification fails"""

    default_message = "HAWK signature verification failed"


class ExpiredHawkTokenException(AuthenticationException):
    """Raised when HAWK token has expired"""

    default_message = "HAWK token has expired"


class InvalidGenerationException(AuthenticationException):
    """Raised when HAWK token has an outdated generation number"""

    default_message = "HAWK token generation number is outdated"
