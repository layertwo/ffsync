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
        """Test converting to Response returns Mozilla code (Requirement 13.1, 13.5)"""
        exc = QuotaExceededException("Quota exceeded")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.INSUFFICIENT_STORAGE
        # Should return integer Mozilla response code 14
        assert response.body == "14"


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

    def test_to_response_returns_mozilla_code(self):
        """Test converting exception to Response returns Mozilla code (Requirement 13.1, 13.7)"""
        from src.shared.exceptions import ServerLimitExceededException

        exc = ServerLimitExceededException("Server limit exceeded")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content_type == "application/json"
        # Should return integer Mozilla response code, not JSON object
        assert response.body == "17"


class TestQuotaExceededExceptionMozillaCode:
    """Tests for QuotaExceededException Mozilla response code"""

    def test_to_response_returns_mozilla_code(self):
        """Test converting exception to Response returns Mozilla code (Requirement 13.1, 13.5)"""
        exc = QuotaExceededException("Quota exceeded")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.INSUFFICIENT_STORAGE
        assert response.content_type == "application/json"
        # Should return integer Mozilla response code 14
        assert response.body == "14"


class TestInvalidBSOException:
    """Tests for InvalidBSOException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        from src.shared.exceptions import InvalidBSOException

        exc = InvalidBSOException()

        assert exc.message == "Invalid BSO"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "InvalidBSOException"
        assert exc.mozilla_code == 8

    def test_to_response_returns_mozilla_code(self):
        """Test converting exception to Response returns Mozilla code (Requirement 13.1, 13.3)"""
        from src.shared.exceptions import InvalidBSOException

        exc = InvalidBSOException("Invalid BSO payload")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content_type == "application/json"
        # Should return integer Mozilla response code 8
        assert response.body == "8"


class TestInvalidCollectionException:
    """Tests for InvalidCollectionException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        from src.shared.exceptions import InvalidCollectionException

        exc = InvalidCollectionException()

        assert exc.message == "Invalid collection name"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "InvalidCollectionException"
        assert exc.mozilla_code == 13

    def test_to_response_returns_mozilla_code(self):
        """Test converting exception to Response returns Mozilla code (Requirement 13.1, 13.4)"""
        from src.shared.exceptions import InvalidCollectionException

        exc = InvalidCollectionException("Collection name too long")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content_type == "application/json"
        # Should return integer Mozilla response code 13
        assert response.body == "13"


class TestJSONParseException:
    """Tests for JSONParseException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        from src.shared.exceptions import JSONParseException

        exc = JSONParseException()

        assert exc.message == "JSON parse failure"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "JSONParseException"
        assert exc.mozilla_code == 6

    def test_to_response_returns_mozilla_code(self):
        """Test converting exception to Response returns Mozilla code (Requirement 13.1, 13.2)"""
        from src.shared.exceptions import JSONParseException

        exc = JSONParseException("Malformed JSON")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content_type == "application/json"
        # Should return integer Mozilla response code 6
        assert response.body == "6"


class TestIncompatibleClientException:
    """Tests for IncompatibleClientException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        from src.shared.exceptions import IncompatibleClientException

        exc = IncompatibleClientException()

        assert exc.message == "Incompatible client"
        assert exc.status_code == HTTPStatus.BAD_REQUEST
        assert exc.error_code == "IncompatibleClientException"
        assert exc.mozilla_code == 16

    def test_to_response_returns_mozilla_code(self):
        """Test converting exception to Response returns Mozilla code (Requirement 13.1, 13.6)"""
        from src.shared.exceptions import IncompatibleClientException

        exc = IncompatibleClientException("Client version not supported")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.content_type == "application/json"
        # Should return integer Mozilla response code 16
        assert response.body == "16"


class TestOptionalResponseHeaders:
    """Tests for optional response headers (Requirements 5.7, 18.1-18.4)"""

    def test_retry_after_header(self):
        """Test Retry-After header on ConflictException (Requirement 5.7)"""
        exc = ConflictException("Resource conflict", retry_after=30)
        response = exc.to_response()

        assert response.status_code == HTTPStatus.CONFLICT
        assert response.headers is not None
        assert response.headers.get("Retry-After") == "30"

    def test_x_weave_backoff_header(self):
        """Test X-Weave-Backoff header (Requirement 18.1)"""
        exc = ServiceUnavailableError("Server under load", backoff=60)
        response = exc.to_response()

        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.headers is not None
        assert response.headers.get("X-Weave-Backoff") == "60"

    def test_x_weave_alert_header(self):
        """Test X-Weave-Alert header (Requirement 18.3)"""
        exc = ServiceUnavailableError("Service decommissioned", alert="hard-eol")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.headers is not None
        assert response.headers.get("X-Weave-Alert") == "hard-eol"

    def test_multiple_optional_headers(self):
        """Test multiple optional headers together"""
        exc = ConflictException(
            "Conflict detected", retry_after=15, backoff=30, alert="Please retry"
        )
        response = exc.to_response()

        assert response.status_code == HTTPStatus.CONFLICT
        assert response.headers is not None
        assert response.headers.get("Retry-After") == "15"
        assert response.headers.get("X-Weave-Backoff") == "30"
        assert response.headers.get("X-Weave-Alert") == "Please retry"

    def test_no_optional_headers_by_default(self):
        """Test that optional headers are not present by default"""
        exc = ValidationException("Invalid input")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.BAD_REQUEST
        # Headers should be None or empty when no optional headers are set
        if response.headers is not None:
            assert "Retry-After" not in response.headers
            assert "X-Weave-Backoff" not in response.headers
            assert "X-Weave-Alert" not in response.headers


class TestTokenServerExceptionsWithKwargs:
    """Test Token Server exceptions accept **kwargs for optional headers"""

    def test_invalid_timestamp_error_with_kwargs(self):
        """Test InvalidTimestampError accepts optional headers"""
        from src.shared.exceptions import InvalidTimestampError

        exc = InvalidTimestampError("Timestamp mismatch", retry_after=10)
        response = exc.to_response()

        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.headers is not None
        assert response.headers.get("Retry-After") == "10"

    def test_invalid_generation_error_with_kwargs(self):
        """Test InvalidGenerationError accepts optional headers"""
        from src.shared.exceptions import InvalidGenerationError

        exc = InvalidGenerationError("Generation outdated", alert="Please re-authenticate")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.headers is not None
        assert response.headers.get("X-Weave-Alert") == "Please re-authenticate"

    def test_invalid_client_state_error_with_kwargs(self):
        """Test InvalidClientStateError accepts optional headers"""
        from src.shared.exceptions import InvalidClientStateError

        exc = InvalidClientStateError("Invalid state", backoff=5)
        response = exc.to_response()

        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.headers is not None
        assert response.headers.get("X-Weave-Backoff") == "5"

    def test_new_users_disabled_error_with_kwargs(self):
        """Test NewUsersDisabledError accepts optional headers"""
        from src.shared.exceptions import NewUsersDisabledError

        exc = NewUsersDisabledError("Registration disabled", alert="Service closed")
        response = exc.to_response()

        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert response.headers is not None
        assert response.headers.get("X-Weave-Alert") == "Service closed"
