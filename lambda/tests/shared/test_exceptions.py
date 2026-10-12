"""Tests for exception classes"""

from http import HTTPStatus

import pytest

from src.shared.exceptions import (
    AuthenticationException,
    CollectionNotFoundException,
    ConflictException,
    ExpiredHawkTokenException,
    IncompatibleClientException,
    InvalidBSOException,
    InvalidCollectionException,
    InvalidCredentialsError,
    InvalidGenerationException,
    InvalidHawkHeaderException,
    InvalidHawkSignatureException,
    InvalidTokenError,
    JSONParseException,
    MethodNotAllowedException,
    PreconditionFailedException,
    QuotaExceededException,
    RequestTooLargeException,
    ServerLimitExceededException,
    ServiceUnavailableError,
    StorageObjectNotFoundException,
    SyncStorageException,
    TokenValidationError,
    UnsupportedMediaTypeException,
    ValidationException,
)


class TestSyncStorageException:
    """Tests for SyncStorageException base class"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = SyncStorageException()

        assert exc.message == "Internal server error"
        assert exc.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc.error_code == "InternalServerError"
        assert str(exc) == "Internal server error"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = SyncStorageException("Custom error message")

        assert exc.message == "Custom error message"
        assert str(exc) == "Custom error message"


class TestValidationException:
    """Tests for ValidationException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = ValidationException()

        assert exc.message == "Invalid request parameters"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "ValidationException"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = ValidationException("Invalid collection name")

        assert exc.message == "Invalid collection name"
        assert str(exc) == "Invalid collection name"


class TestConflictException:
    """Tests for ConflictException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = ConflictException()

        assert exc.message == "Resource conflict"
        assert exc.status_code == HTTPStatus.CONFLICT
        assert exc.error_code == "ConflictException"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = ConflictException("Collection already exists")

        assert exc.message == "Collection already exists"


class TestPreconditionFailedException:
    """Tests for PreconditionFailedException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = PreconditionFailedException()

        assert exc.message == "Precondition failed"
        assert exc.status_code == HTTPStatus.PRECONDITION_FAILED
        assert exc.error_code == "PreconditionFailedException"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = PreconditionFailedException("Modified since check failed")

        assert exc.message == "Modified since check failed"


class TestQuotaExceededException:
    """Tests for QuotaExceededException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = QuotaExceededException()

        assert exc.message == "Storage quota exceeded"
        assert exc.status_code == HTTPStatus.INSUFFICIENT_STORAGE
        assert exc.error_code == "QuotaExceededException"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = QuotaExceededException("Maximum storage limit reached")

        assert exc.message == "Maximum storage limit reached"


class TestCollectionNotFoundException:
    """Tests for CollectionNotFoundException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = CollectionNotFoundException()

        assert exc.message == "Collection not found"
        assert exc.status_code == HTTPStatus.NOT_FOUND
        assert exc.error_code == "CollectionNotFoundException"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = CollectionNotFoundException("Collection 'bookmarks' not found")

        assert exc.message == "Collection 'bookmarks' not found"


class TestStorageObjectNotFoundException:
    """Tests for StorageObjectNotFoundException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = StorageObjectNotFoundException()

        assert exc.message == "Storage object not found"
        assert exc.status_code == HTTPStatus.NOT_FOUND
        assert exc.error_code == "StorageObjectNotFoundException"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = StorageObjectNotFoundException("Object 'item123' not found")

        assert exc.message == "Object 'item123' not found"


class TestAuthenticationException:
    """Tests for AuthenticationException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = AuthenticationException()

        assert exc.message == "Authentication required"
        assert exc.status_code == HTTPStatus.UNAUTHORIZED
        assert exc.error_code == "AuthenticationException"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = AuthenticationException("Invalid credentials")

        assert exc.message == "Invalid credentials"


class TestExceptionInheritance:
    """Test exception inheritance"""

    def test_all_exceptions_inherit_from_base(self) -> None:
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

    def test_exceptions_are_raisable(self) -> None:
        """Test that exceptions can be raised and caught"""
        with pytest.raises(ValidationException) as exc_info:
            raise ValidationException("Test error")

        assert exc_info.value.message == "Test error"

        with pytest.raises(SyncStorageException):
            raise ValidationException("Test error")


# Token Server Exception Tests


class TestInvalidTokenError:
    """Tests for InvalidTokenError exception"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""

        exc = InvalidTokenError()

        assert exc.message == "Invalid or expired token"
        assert exc.status_code == HTTPStatus.UNAUTHORIZED
        assert exc.error_code == "InvalidTokenError"
        assert str(exc) == "Invalid or expired token"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = InvalidTokenError("Token signature verification failed")

        assert exc.message == "Token signature verification failed"
        assert str(exc) == "Token signature verification failed"


class TestInvalidCredentialsError:
    """Tests for InvalidCredentialsError exception"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""

        exc = InvalidCredentialsError()

        assert exc.message == "Invalid credentials"
        assert exc.status_code == HTTPStatus.UNAUTHORIZED
        assert exc.error_code == "InvalidCredentialsError"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = InvalidCredentialsError("Authentication failed")

        assert exc.message == "Authentication failed"


class TestTokenValidationError:
    """Tests for TokenValidationError exception"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""

        exc = TokenValidationError()

        assert exc.message == "Token validation failed"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "ValidationException"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = TokenValidationError("Invalid token format")

        assert exc.message == "Invalid token format"

    def test_inherits_from_validation_exception(self) -> None:
        """Test that TokenValidationError inherits from ValidationException"""
        exc = TokenValidationError()

        assert isinstance(exc, ValidationException)
        assert isinstance(exc, SyncStorageException)


class TestServiceUnavailableError:
    """Tests for ServiceUnavailableError exception"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""

        exc = ServiceUnavailableError()

        assert exc.message == "Service temporarily unavailable"
        assert exc.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert exc.error_code == "ServiceUnavailableError"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = ServiceUnavailableError("OIDC provider unreachable")

        assert exc.message == "OIDC provider unreachable"


class TestRequestTooLargeException:
    """Tests for RequestTooLargeException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = RequestTooLargeException()

        assert exc.message == "Request entity too large"
        assert exc.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        assert exc.error_code == "RequestTooLargeException"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = RequestTooLargeException("Payload exceeds 2MB limit")

        assert exc.message == "Payload exceeds 2MB limit"


class TestMethodNotAllowedException:
    """Tests for MethodNotAllowedException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = MethodNotAllowedException()

        assert exc.message == "Method not allowed"
        assert exc.status_code == HTTPStatus.METHOD_NOT_ALLOWED
        assert exc.error_code == "MethodNotAllowedException"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = MethodNotAllowedException("POST not allowed on this resource")

        assert exc.message == "POST not allowed on this resource"


class TestUnsupportedMediaTypeException:
    """Tests for UnsupportedMediaTypeException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = UnsupportedMediaTypeException()

        assert exc.message == "Unsupported media type"
        assert exc.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        assert exc.error_code == "UnsupportedMediaTypeException"

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = UnsupportedMediaTypeException("Content-Type must be application/json")

        assert exc.message == "Content-Type must be application/json"


class TestServerLimitExceededException:
    """Tests for ServerLimitExceededException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = ServerLimitExceededException()

        assert exc.message == "Server limit exceeded"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "ServerLimitExceededException"
        assert exc.mozilla_code == 17

    def test_custom_message(self) -> None:
        """Test exception with custom message"""
        exc = ServerLimitExceededException("Batch size exceeds 100 records")

        assert exc.message == "Batch size exceeds 100 records"


class TestQuotaExceededExceptionMozillaCode:
    """Tests for QuotaExceededException Mozilla response code"""


class TestInvalidBSOException:
    """Tests for InvalidBSOException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = InvalidBSOException()

        assert exc.message == "Invalid BSO"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "InvalidBSOException"
        assert exc.mozilla_code == 8


class TestInvalidCollectionException:
    """Tests for InvalidCollectionException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = InvalidCollectionException()

        assert exc.message == "Invalid collection name"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "InvalidCollectionException"
        assert exc.mozilla_code == 13


class TestJSONParseException:
    """Tests for JSONParseException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = JSONParseException()

        assert exc.message == "JSON parse failure"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "JSONParseException"
        assert exc.mozilla_code == 6


class TestIncompatibleClientException:
    """Tests for IncompatibleClientException"""

    def test_default_initialization(self) -> None:
        """Test exception with default message"""
        exc = IncompatibleClientException()

        assert exc.message == "Incompatible client"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "IncompatibleClientException"
        assert exc.mozilla_code == 16


class TestOptionalResponseHeaders:
    """Tests for optional response headers (Requirements 5.7, 18.1-18.4)"""


class TestTokenServerExceptionsWithKwargs:
    """Test Token Server exceptions accept **kwargs for optional headers"""


class TestInvalidHawkHeaderException:
    """Tests for InvalidHawkHeaderException"""

    def test_default_initialization(self) -> None:
        """Test default initialization"""
        exception = InvalidHawkHeaderException()
        assert exception.message == "Malformed HAWK Authorization header"
        assert exception.status_code == HTTPStatus.UNAUTHORIZED

    def test_custom_message(self) -> None:
        """Test custom message"""
        exception = InvalidHawkHeaderException("Custom HAWK header error")
        assert exception.message == "Custom HAWK header error"


class TestInvalidHawkSignatureException:
    """Tests for InvalidHawkSignatureException"""

    def test_default_initialization(self) -> None:
        """Test default initialization"""
        exception = InvalidHawkSignatureException()
        assert exception.message == "HAWK signature verification failed"
        assert exception.status_code == HTTPStatus.UNAUTHORIZED

    def test_custom_message(self) -> None:
        """Test custom message"""
        exception = InvalidHawkSignatureException("Signature mismatch")
        assert exception.message == "Signature mismatch"


class TestExpiredHawkTokenException:
    """Tests for ExpiredHawkTokenException"""

    def test_default_initialization(self) -> None:
        """Test default initialization"""
        exception = ExpiredHawkTokenException()
        assert exception.message == "HAWK token has expired"
        assert exception.status_code == HTTPStatus.UNAUTHORIZED

    def test_custom_message(self) -> None:
        """Test custom message"""
        exception = ExpiredHawkTokenException("Token expired at 1234567890")
        assert exception.message == "Token expired at 1234567890"


class TestInvalidGenerationException:
    """Tests for InvalidGenerationException"""

    def test_default_initialization(self) -> None:
        """Test default initialization"""
        exception = InvalidGenerationException()
        assert exception.message == "HAWK token generation number is outdated"
        assert exception.status_code == HTTPStatus.UNAUTHORIZED

    def test_custom_message(self) -> None:
        """Test custom message"""
        exception = InvalidGenerationException("Generation mismatch: expected 5, got 3")
        assert exception.message == "Generation mismatch: expected 5, got 3"


class TestHawkExceptionInheritance:
    """Tests for HAWK exception inheritance"""

    def test_hawk_exceptions_inherit_from_authentication_exception(self) -> None:
        """Test that all HAWK exceptions inherit from AuthenticationException"""
        assert issubclass(InvalidHawkHeaderException, AuthenticationException)
        assert issubclass(InvalidHawkSignatureException, AuthenticationException)
        assert issubclass(ExpiredHawkTokenException, AuthenticationException)
        assert issubclass(InvalidGenerationException, AuthenticationException)

    def test_hawk_exceptions_are_raisable(self) -> None:
        """Test that HAWK exceptions can be raised and caught"""

        with pytest.raises(InvalidHawkHeaderException):
            raise InvalidHawkHeaderException("Test")

        with pytest.raises(InvalidHawkSignatureException):
            raise InvalidHawkSignatureException("Test")

        with pytest.raises(ExpiredHawkTokenException):
            raise ExpiredHawkTokenException("Test")

        with pytest.raises(InvalidGenerationException):
            raise InvalidGenerationException("Test")
