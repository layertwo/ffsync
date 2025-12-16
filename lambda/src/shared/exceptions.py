from http import HTTPStatus

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

    def __init__(self, message: str = "Internal server error"):
        self.message = message
        super().__init__(self.message)

    def to_response(self) -> Response:
        return Response(
            status_code=self.status_code,
            content_type="application/json",
            body=f'{{"error": "{self.error_code}", "message": "{self.message}"}}',
        )


class ValidationException(SyncStorageException):
    """Validation error exception"""

    status_code = HTTPStatus.BAD_REQUEST
    error_code = "ValidationException"

    def __init__(self, message: str = "Invalid request parameters"):
        super().__init__(message)


class ConflictException(SyncStorageException):
    """Conflict error exception"""

    status_code = HTTPStatus.CONFLICT
    error_code = "ConflictException"

    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message)


class PreconditionFailedException(SyncStorageException):
    """Precondition failed exception"""

    status_code = HTTPStatus.PRECONDITION_FAILED
    error_code = "PreconditionFailedException"

    def __init__(self, message: str = "Precondition failed"):
        super().__init__(message)


class QuotaExceededException(SyncStorageException):
    """Quota exceeded exception"""

    status_code = HTTPStatus.INSUFFICIENT_STORAGE
    error_code = "QuotaExceededException"

    def __init__(self, message: str = "Storage quota exceeded"):
        super().__init__(message)


class CollectionNotFoundException(SyncStorageException):
    """Collection not found exception"""

    status_code = HTTPStatus.NOT_FOUND
    error_code = "CollectionNotFoundException"

    def __init__(self, message: str = "Collection not found"):
        super().__init__(message)


class StorageObjectNotFoundException(SyncStorageException):
    """Storage object not found exception"""

    status_code = HTTPStatus.NOT_FOUND
    error_code = "StorageObjectNotFoundException"

    def __init__(self, message: str = "Storage object not found"):
        super().__init__(message)


class AuthenticationException(SyncStorageException):
    """Authentication error exception"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "AuthenticationException"

    def __init__(self, message: str = "Authentication required"):
        super().__init__(message)


class RequestTooLargeException(SyncStorageException):
    """Request entity too large exception"""

    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    error_code = "RequestTooLargeException"

    def __init__(self, message: str = "Request entity too large"):
        super().__init__(message)


class MethodNotAllowedException(SyncStorageException):
    """Method not allowed exception"""

    status_code = HTTPStatus.METHOD_NOT_ALLOWED
    error_code = "MethodNotAllowedException"

    def __init__(self, message: str = "Method not allowed"):
        super().__init__(message)


class UnsupportedMediaTypeException(SyncStorageException):
    """Unsupported media type exception"""

    status_code = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    error_code = "UnsupportedMediaTypeException"

    def __init__(self, message: str = "Unsupported media type"):
        super().__init__(message)


class ServerLimitExceededException(SyncStorageException):
    """Server limit exceeded exception (Mozilla response code 17)"""

    status_code = HTTPStatus.BAD_REQUEST
    error_code = "ServerLimitExceededException"
    mozilla_code = 17

    def __init__(self, message: str = "Server limit exceeded"):
        super().__init__(message)


# Token Server specific exceptions


class InvalidTokenError(SyncStorageException):
    """Raised when an OIDC token is invalid or cannot be validated"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "InvalidTokenError"

    def __init__(self, message: str = "Invalid or expired token"):
        super().__init__(message)


class InvalidCredentialsError(SyncStorageException):
    """Raised when authentication credentials are invalid"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "InvalidCredentialsError"

    def __init__(self, message: str = "Invalid credentials"):
        super().__init__(message)


class TokenValidationError(ValidationException):
    """Raised when token validation fails"""

    def __init__(self, message: str = "Token validation failed"):
        super().__init__(message)


class ServiceUnavailableError(SyncStorageException):
    """Raised when external services (OIDC provider, DynamoDB) are unavailable"""

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    error_code = "ServiceUnavailableError"

    def __init__(self, message: str = "Service temporarily unavailable"):
        super().__init__(message)


class InvalidTimestampError(SyncStorageException):
    """Raised when OIDC token timestamp differs significantly from server time"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "InvalidTimestampError"
    status_field = "invalid-timestamp"

    def __init__(self, message: str = "Token timestamp differs significantly from server time"):
        super().__init__(message)


class InvalidGenerationError(SyncStorageException):
    """Raised when bearer token has an outdated generation number"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "InvalidGenerationError"
    status_field = "invalid-generation"

    def __init__(self, message: str = "Token generation number is outdated"):
        super().__init__(message)


class InvalidClientStateError(SyncStorageException):
    """Raised when client state transition is invalid (e.g., previously-seen state)"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "InvalidClientStateError"
    status_field = "invalid-client-state"

    def __init__(self, message: str = "Invalid client state transition"):
        super().__init__(message)


class NewUsersDisabledError(SyncStorageException):
    """Raised when new user registration is disabled and user doesn't exist"""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "NewUsersDisabledError"
    status_field = "new-users-disabled"

    def __init__(self, message: str = "New user registration is disabled"):
        super().__init__(message)
