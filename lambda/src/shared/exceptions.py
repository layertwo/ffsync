from typing import Any, Dict

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


class RequestTooLargeException(SyncStorageException):
    """Request too large exception"""

    status_code = StatusCode.REQUEST_TOO_LARGE
    error_code = "RequestTooLargeException"

    def __init__(self, message: str = "Request entity too large"):
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


class AuthenticationException(SyncStorageException):
    """Authentication error exception"""

    status_code = StatusCode.UNAUTHORIZED
    error_code = "AuthenticationException"

    def __init__(self, message: str = "Authentication required"):
        super().__init__(message)
