"""Tests for exception classes"""

import json
from http import HTTPStatus

import pytest

from src.shared.exceptions import (
    AuthenticationException,
    CollectionNotFoundException,
    ConflictException,
    InvalidCredentialsError,
    InvalidTokenError,
    PreconditionFailedException,
    QuotaExceededException,
    ServiceUnavailableError,
    StorageObjectNotFoundException,
    SyncStorageException,
    TokenValidationError,
    ValidationException,
)


class TestSyncStorageException:
    """Tests for SyncStorageException base class"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = SyncStorageException()

        assert exc.message == "Internal server error"
        assert exc.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc.error_code == "InternalServerError"
        assert str(exc) == "Internal server error"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = SyncStorageException("Custom error message")

        assert exc.message == "Custom error message"
        assert str(exc) == "Custom error message"

    def test_to_response(self):
        """Test converting exception to Response"""
        exc = SyncStorageException("Test error")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert response.content_type == "application/json"

        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "InternalServerError"
        assert body["message"] == "Test error"


class TestValidationException:
    """Tests for ValidationException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = ValidationException()

        assert exc.message == "Invalid request parameters"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "ValidationException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = ValidationException("Invalid collection name")

        assert exc.message == "Invalid collection name"
        assert str(exc) == "Invalid collection name"

    def test_to_response(self):
        """Test converting to Response"""
        exc = ValidationException("Invalid input")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "ValidationException"
        assert body["message"] == "Invalid input"


class TestConflictException:
    """Tests for ConflictException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = ConflictException()

        assert exc.message == "Resource conflict"
        assert exc.status_code == HTTPStatus.CONFLICT
        assert exc.error_code == "ConflictException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = ConflictException("Collection already exists")

        assert exc.message == "Collection already exists"

    def test_to_response(self):
        """Test converting to Response"""
        exc = ConflictException("Conflict detected")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.CONFLICT
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "ConflictException"


class TestPreconditionFailedException:
    """Tests for PreconditionFailedException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = PreconditionFailedException()

        assert exc.message == "Precondition failed"
        assert exc.status_code == HTTPStatus.PRECONDITION_FAILED
        assert exc.error_code == "PreconditionFailedException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = PreconditionFailedException("Modified since check failed")

        assert exc.message == "Modified since check failed"

    def test_to_response(self):
        """Test converting to Response"""
        exc = PreconditionFailedException("Precondition not met")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.PRECONDITION_FAILED
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "PreconditionFailedException"


class TestQuotaExceededException:
    """Tests for QuotaExceededException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = QuotaExceededException()

        assert exc.message == "Storage quota exceeded"
        assert exc.status_code == HTTPStatus.INSUFFICIENT_STORAGE
        assert exc.error_code == "QuotaExceededException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = QuotaExceededException("Maximum storage limit reached")

        assert exc.message == "Maximum storage limit reached"

    def test_to_response(self):
        """Test converting to Response"""
        exc = QuotaExceededException("Quota exceeded")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.INSUFFICIENT_STORAGE
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "QuotaExceededException"


class TestCollectionNotFoundException:
    """Tests for CollectionNotFoundException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = CollectionNotFoundException()

        assert exc.message == "Collection not found"
        assert exc.status_code == HTTPStatus.NOT_FOUND
        assert exc.error_code == "CollectionNotFoundException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = CollectionNotFoundException("Collection 'bookmarks' not found")

        assert exc.message == "Collection 'bookmarks' not found"

    def test_to_response(self):
        """Test converting to Response"""
        exc = CollectionNotFoundException("Not found")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "CollectionNotFoundException"


class TestStorageObjectNotFoundException:
    """Tests for StorageObjectNotFoundException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = StorageObjectNotFoundException()

        assert exc.message == "Storage object not found"
        assert exc.status_code == HTTPStatus.NOT_FOUND
        assert exc.error_code == "StorageObjectNotFoundException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = StorageObjectNotFoundException("Object 'item123' not found")

        assert exc.message == "Object 'item123' not found"

    def test_to_response(self):
        """Test converting to Response"""
        exc = StorageObjectNotFoundException("Object missing")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "StorageObjectNotFoundException"


class TestAuthenticationException:
    """Tests for AuthenticationException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = AuthenticationException()

        assert exc.message == "Authentication required"
        assert exc.status_code == HTTPStatus.UNAUTHORIZED
        assert exc.error_code == "AuthenticationException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = AuthenticationException("Invalid credentials")

        assert exc.message == "Invalid credentials"

    def test_to_response(self):
        """Test converting to Response"""
        exc = AuthenticationException("Auth failed")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "AuthenticationException"


class TestExceptionInheritance:
    """Test exception inheritance"""

    def test_all_exceptions_inherit_from_base(self):
        """Test that all custom exceptions inherit from SyncStorageException"""
        exceptions = [
            ValidationException(),
            ConflictException(),
            PreconditionFailedException(),
            QuotaExceededException(),
            CollectionNotFoundException(),
            StorageObjectNotFoundException(),
            AuthenticationException(),
        ]

        for exc in exceptions:
            assert isinstance(exc, SyncStorageException)
            assert isinstance(exc, Exception)

    def test_exceptions_are_raisable(self):
        """Test that exceptions can be raised and caught"""
        with pytest.raises(ValidationException) as exc_info:
            raise ValidationException("Test error")

        assert exc_info.value.message == "Test error"

        with pytest.raises(SyncStorageException):
            raise ValidationException("Test error")


# Token Server Exception Tests


class TestInvalidTokenError:
    """Tests for InvalidTokenError exception"""

    def test_default_initialization(self):
        """Test exception with default message"""

        exc = InvalidTokenError()

        assert exc.message == "Invalid or expired token"
        assert exc.status_code == HTTPStatus.UNAUTHORIZED
        assert exc.error_code == "InvalidTokenError"
        assert str(exc) == "Invalid or expired token"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = InvalidTokenError("Token signature verification failed")

        assert exc.message == "Token signature verification failed"
        assert str(exc) == "Token signature verification failed"

    def test_to_response(self):
        """Test converting exception to Response"""
        exc = InvalidTokenError("Token expired")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.content_type == "application/json"

        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "InvalidTokenError"
        assert body["message"] == "Token expired"


class TestInvalidCredentialsError:
    """Tests for InvalidCredentialsError exception"""

    def test_default_initialization(self):
        """Test exception with default message"""

        exc = InvalidCredentialsError()

        assert exc.message == "Invalid credentials"
        assert exc.status_code == HTTPStatus.UNAUTHORIZED
        assert exc.error_code == "InvalidCredentialsError"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = InvalidCredentialsError("Authentication failed")

        assert exc.message == "Authentication failed"

    def test_to_response(self):
        """Test converting exception to Response"""
        exc = InvalidCredentialsError("Bad credentials")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "InvalidCredentialsError"


class TestTokenValidationError:
    """Tests for TokenValidationError exception"""

    def test_default_initialization(self):
        """Test exception with default message"""

        exc = TokenValidationError()

        assert exc.message == "Token validation failed"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "ValidationException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = TokenValidationError("Invalid token format")

        assert exc.message == "Invalid token format"

    def test_inherits_from_validation_exception(self):
        """Test that TokenValidationError inherits from ValidationException"""
        exc = TokenValidationError()

        assert isinstance(exc, ValidationException)
        assert isinstance(exc, SyncStorageException)

    def test_to_response(self):
        """Test converting exception to Response"""
        exc = TokenValidationError("Malformed token")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "ValidationException"


class TestServiceUnavailableError:
    """Tests for ServiceUnavailableError exception"""

    def test_default_initialization(self):
        """Test exception with default message"""

        exc = ServiceUnavailableError()

        assert exc.message == "Service temporarily unavailable"
        assert exc.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert exc.error_code == "ServiceUnavailableError"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = ServiceUnavailableError("OIDC provider unreachable")

        assert exc.message == "OIDC provider unreachable"

    def test_to_response(self):
        """Test converting exception to Response"""
        exc = ServiceUnavailableError("Database connection failed")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.content_type == "application/json"

        assert response.body is not None
        body = json.loads(response.body)
        assert body["error"] == "ServiceUnavailableError"
        assert body["message"] == "Database connection failed"


class TestRequestTooLargeException:
    """Tests for RequestTooLargeException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        from src.shared.exceptions import RequestTooLargeException

        exc = RequestTooLargeException()

        assert exc.message == "Request entity too large"
        assert exc.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        assert exc.error_code == "RequestTooLargeException"

    def test_custom_message(self):
        """Test exception with custom message"""
        from src.shared.exceptions import RequestTooLargeException

        exc = RequestTooLargeException("Payload exceeds 2MB limit")

        assert exc.message == "Payload exceeds 2MB limit"

    def test_to_response(self):
        """Test converting exception to Response"""
        from src.shared.exceptions import RequestTooLargeException

        exc = RequestTooLargeException("Request too large")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        assert response.content_type == "application/json"


class TestMethodNotAllowedException:
    """Tests for MethodNotAllowedException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        from src.shared.exceptions import MethodNotAllowedException

        exc = MethodNotAllowedException()

        assert exc.message == "Method not allowed"
        assert exc.status_code == HTTPStatus.METHOD_NOT_ALLOWED
        assert exc.error_code == "MethodNotAllowedException"

    def test_custom_message(self):
        """Test exception with custom message"""
        from src.shared.exceptions import MethodNotAllowedException

        exc = MethodNotAllowedException("POST not allowed on this resource")

        assert exc.message == "POST not allowed on this resource"

    def test_to_response(self):
        """Test converting exception to Response"""
        from src.shared.exceptions import MethodNotAllowedException

        exc = MethodNotAllowedException("Method not allowed")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
        assert response.content_type == "application/json"


class TestUnsupportedMediaTypeException:
    """Tests for UnsupportedMediaTypeException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        from src.shared.exceptions import UnsupportedMediaTypeException

        exc = UnsupportedMediaTypeException()

        assert exc.message == "Unsupported media type"
        assert exc.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        assert exc.error_code == "UnsupportedMediaTypeException"

    def test_custom_message(self):
        """Test exception with custom message"""
        from src.shared.exceptions import UnsupportedMediaTypeException

        exc = UnsupportedMediaTypeException("Content-Type must be application/json")

        assert exc.message == "Content-Type must be application/json"

    def test_to_response(self):
        """Test converting exception to Response"""
        from src.shared.exceptions import UnsupportedMediaTypeException

        exc = UnsupportedMediaTypeException("Unsupported media type")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        assert response.content_type == "application/json"


class TestServerLimitExceededException:
    """Tests for ServerLimitExceededException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        from src.shared.exceptions import ServerLimitExceededException

        exc = ServerLimitExceededException()

        assert exc.message == "Server limit exceeded"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "ServerLimitExceededException"
        assert exc.mozilla_code == 17

    def test_custom_message(self):
        """Test exception with custom message"""
        from src.shared.exceptions import ServerLimitExceededException

        exc = ServerLimitExceededException("Batch size exceeds 100 records")

        assert exc.message == "Batch size exceeds 100 records"

    def test_to_response(self):
        """Test converting exception to Response"""
        from src.shared.exceptions import ServerLimitExceededException

        exc = ServerLimitExceededException("Server limit exceeded")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content_type == "application/json"
