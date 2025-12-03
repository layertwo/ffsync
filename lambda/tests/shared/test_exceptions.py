"""Tests for exception classes"""

import json

import pytest
from aws_lambda_proxy import StatusCode

from src.shared.exceptions import (
    AuthenticationException,
    CollectionNotFoundException,
    ConflictException,
    PreconditionFailedException,
    QuotaExceededException,
    StorageObjectNotFoundException,
    SyncStorageException,
    ValidationException,
)


class TestSyncStorageException:
    """Tests for SyncStorageException base class"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = SyncStorageException()

        assert exc.message == "Internal server error"
        assert exc.status_code == StatusCode.INTERNAL_SERVER_ERROR
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

        assert response.status_code == StatusCode.INTERNAL_SERVER_ERROR
        assert response.content_type == "application/json"

        body = json.loads(response.body)
        assert body["error"] == "InternalServerError"
        assert body["message"] == "Test error"


class TestValidationException:
    """Tests for ValidationException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = ValidationException()

        assert exc.message == "Invalid request parameters"
        assert exc.status_code == StatusCode.BAD_REQUEST
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

        assert response.status_code == StatusCode.BAD_REQUEST
        body = json.loads(response.body)
        assert body["error"] == "ValidationException"
        assert body["message"] == "Invalid input"


class TestConflictException:
    """Tests for ConflictException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = ConflictException()

        assert exc.message == "Resource conflict"
        assert exc.status_code == StatusCode.CONFLICT
        assert exc.error_code == "ConflictException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = ConflictException("Collection already exists")

        assert exc.message == "Collection already exists"

    def test_to_response(self):
        """Test converting to Response"""
        exc = ConflictException("Conflict detected")
        response = exc.to_response()

        assert response.status_code == StatusCode.CONFLICT
        body = json.loads(response.body)
        assert body["error"] == "ConflictException"


class TestPreconditionFailedException:
    """Tests for PreconditionFailedException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = PreconditionFailedException()

        assert exc.message == "Precondition failed"
        assert exc.status_code == StatusCode.PRECONDITION_FAILED
        assert exc.error_code == "PreconditionFailedException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = PreconditionFailedException("Modified since check failed")

        assert exc.message == "Modified since check failed"

    def test_to_response(self):
        """Test converting to Response"""
        exc = PreconditionFailedException("Precondition not met")
        response = exc.to_response()

        assert response.status_code == StatusCode.PRECONDITION_FAILED
        body = json.loads(response.body)
        assert body["error"] == "PreconditionFailedException"


class TestQuotaExceededException:
    """Tests for QuotaExceededException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = QuotaExceededException()

        assert exc.message == "Storage quota exceeded"
        assert exc.status_code == StatusCode.INSUFFICIENT_STORAGE
        assert exc.error_code == "QuotaExceededException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = QuotaExceededException("Maximum storage limit reached")

        assert exc.message == "Maximum storage limit reached"

    def test_to_response(self):
        """Test converting to Response"""
        exc = QuotaExceededException("Quota exceeded")
        response = exc.to_response()

        assert response.status_code == StatusCode.INSUFFICIENT_STORAGE
        body = json.loads(response.body)
        assert body["error"] == "QuotaExceededException"


class TestCollectionNotFoundException:
    """Tests for CollectionNotFoundException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = CollectionNotFoundException()

        assert exc.message == "Collection not found"
        assert exc.status_code == StatusCode.NOT_FOUND
        assert exc.error_code == "CollectionNotFoundException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = CollectionNotFoundException("Collection 'bookmarks' not found")

        assert exc.message == "Collection 'bookmarks' not found"

    def test_to_response(self):
        """Test converting to Response"""
        exc = CollectionNotFoundException("Not found")
        response = exc.to_response()

        assert response.status_code == StatusCode.NOT_FOUND
        body = json.loads(response.body)
        assert body["error"] == "CollectionNotFoundException"


class TestStorageObjectNotFoundException:
    """Tests for StorageObjectNotFoundException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = StorageObjectNotFoundException()

        assert exc.message == "Storage object not found"
        assert exc.status_code == StatusCode.NOT_FOUND
        assert exc.error_code == "StorageObjectNotFoundException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = StorageObjectNotFoundException("Object 'item123' not found")

        assert exc.message == "Object 'item123' not found"

    def test_to_response(self):
        """Test converting to Response"""
        exc = StorageObjectNotFoundException("Object missing")
        response = exc.to_response()

        assert response.status_code == StatusCode.NOT_FOUND
        body = json.loads(response.body)
        assert body["error"] == "StorageObjectNotFoundException"


class TestAuthenticationException:
    """Tests for AuthenticationException"""

    def test_default_initialization(self):
        """Test exception with default message"""
        exc = AuthenticationException()

        assert exc.message == "Authentication required"
        assert exc.status_code == StatusCode.UNAUTHORIZED
        assert exc.error_code == "AuthenticationException"

    def test_custom_message(self):
        """Test exception with custom message"""
        exc = AuthenticationException("Invalid credentials")

        assert exc.message == "Invalid credentials"

    def test_to_response(self):
        """Test converting to Response"""
        exc = AuthenticationException("Auth failed")
        response = exc.to_response()

        assert response.status_code == StatusCode.UNAUTHORIZED
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
