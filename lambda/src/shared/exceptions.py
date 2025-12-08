from aws_lambda_proxy import Response, StatusCode


class SyncStorageException(Exception):
    """Base exception for SyncStorage API"""

    status_code = StatusCode.INTERNAL_SERVER_ERROR
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

    status_code = StatusCode.BAD_REQUEST
    error_code = "ValidationException"

    def __init__(self, message: str = "Invalid request parameters"):
        super().__init__(message)


class ConflictException(SyncStorageException):
    """Conflict error exception"""

    status_code = StatusCode.CONFLICT
    error_code = "ConflictException"

    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message)


class PreconditionFailedException(SyncStorageException):
    """Precondition failed exception"""

    status_code = StatusCode.PRECONDITION_FAILED
    error_code = "PreconditionFailedException"

    def __init__(self, message: str = "Precondition failed"):
        super().__init__(message)


class QuotaExceededException(SyncStorageException):
    """Quota exceeded exception"""

    status_code = StatusCode.INSUFFICIENT_STORAGE
    error_code = "QuotaExceededException"

    def __init__(self, message: str = "Storage quota exceeded"):
        super().__init__(message)


class CollectionNotFoundException(SyncStorageException):
    """Collection not found exception"""

    status_code = StatusCode.NOT_FOUND
    error_code = "CollectionNotFoundException"

    def __init__(self, message: str = "Collection not found"):
        super().__init__(message)


class StorageObjectNotFoundException(SyncStorageException):
    """Storage object not found exception"""

    status_code = StatusCode.NOT_FOUND
    error_code = "StorageObjectNotFoundException"

    def __init__(self, message: str = "Storage object not found"):
        super().__init__(message)


class AuthenticationException(SyncStorageException):
    """Authentication error exception"""

    status_code = StatusCode.UNAUTHORIZED
    error_code = "AuthenticationException"

    def __init__(self, message: str = "Authentication required"):
        super().__init__(message)


# Token Server specific exceptions


class InvalidTokenError(SyncStorageException):
    """Raised when an OIDC token is invalid or cannot be validated"""

    status_code = StatusCode.UNAUTHORIZED
    error_code = "InvalidTokenError"

    def __init__(self, message: str = "Invalid or expired token"):
        super().__init__(message)


class InvalidCredentialsError(SyncStorageException):
    """Raised when authentication credentials are invalid"""

    status_code = StatusCode.UNAUTHORIZED
    error_code = "InvalidCredentialsError"

    def __init__(self, message: str = "Invalid credentials"):
        super().__init__(message)


class TokenValidationError(ValidationException):
    """Raised when token validation fails"""

    def __init__(self, message: str = "Token validation failed"):
        super().__init__(message)


class ServiceUnavailableError(SyncStorageException):
    """Raised when external services (OIDC provider, DynamoDB) are unavailable"""

    status_code = StatusCode.SERVICE_UNAVAILABLE
    error_code = "ServiceUnavailableError"

    def __init__(self, message: str = "Service temporarily unavailable"):
        super().__init__(message)
