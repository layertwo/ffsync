"""Tests for UserRecord model"""

import json

import pytest

from src.shared.user import UserRecord


class TestUserRecord:
    """Tests for UserRecord model"""

    def test_creation_with_all_fields(self):
        """Test creating UserRecord with all fields"""
        user = UserRecord(
            user_id="test_user_123",
            generation=5,
            created_at=1234567890.0,
            updated_at=1234567900.0,
        )

        assert user.user_id == "test_user_123"
        assert user.generation == 5
        assert user.created_at == 1234567890.0
        assert user.updated_at == 1234567900.0

    def test_creation_with_zero_generation(self):
        """Test creating UserRecord with generation 0 (new user)"""
        user = UserRecord(
            user_id="new_user",
            generation=0,
            created_at=1234567890.0,
            updated_at=1234567890.0,
        )

        assert user.generation == 0
        assert user.created_at == user.updated_at

    def test_to_json(self):
        """Test serialization to JSON"""
        user = UserRecord(
            user_id="test_user",
            generation=3,
            created_at=1234567890.0,
            updated_at=1234567900.0,
        )

        json_str = user.to_json()
        data = json.loads(json_str)

        assert data["user_id"] == "test_user"
        assert data["generation"] == 3
        assert data["created_at"] == 1234567890.0
        assert data["updated_at"] == 1234567900.0

    def test_from_json(self):
        """Test deserialization from JSON"""
        json_str = '{"user_id": "test_user", "generation": 7, "created_at": 1234567890.0, "updated_at": 1234567950.0}'
        user = UserRecord.from_json(json_str)

        assert user.user_id == "test_user"
        assert user.generation == 7
        assert user.created_at == 1234567890.0
        assert user.updated_at == 1234567950.0

    def test_round_trip_serialization(self):
        """Test that serialization and deserialization are inverses"""
        original = UserRecord(
            user_id="round_trip_user",
            generation=10,
            created_at=1234567890.12,
            updated_at=1234567999.99,
        )

        json_str = original.to_json()
        restored = UserRecord.from_json(json_str)

        assert restored.user_id == original.user_id
        assert restored.generation == original.generation
        assert restored.created_at == original.created_at
        assert restored.updated_at == original.updated_at

    def test_to_dict(self):
        """Test conversion to dictionary"""
        user = UserRecord(
            user_id="dict_user",
            generation=2,
            created_at=1234567890.0,
            updated_at=1234567900.0,
        )

        data = user.to_dict()

        assert isinstance(data, dict)
        assert data["user_id"] == "dict_user"
        assert data["generation"] == 2
        assert data["created_at"] == 1234567890.0
        assert data["updated_at"] == 1234567900.0

    def test_from_dict(self):
        """Test creation from dictionary"""
        data = {
            "user_id": "dict_user",
            "generation": 4,
            "created_at": 1234567890.0,
            "updated_at": 1234567920.0,
        }

        user = UserRecord.from_dict(data)

        assert user.user_id == "dict_user"
        assert user.generation == 4
        assert user.created_at == 1234567890.0
        assert user.updated_at == 1234567920.0

    def test_updated_at_greater_than_created_at(self):
        """Test that updated_at can be greater than created_at"""
        user = UserRecord(
            user_id="test_user",
            generation=1,
            created_at=1234567890.0,
            updated_at=1234567990.0,
        )

        assert user.updated_at > user.created_at

    def test_generation_monotonicity(self):
        """Test that generation numbers can increase"""
        user1 = UserRecord(
            user_id="test_user",
            generation=5,
            created_at=1234567890.0,
            updated_at=1234567890.0,
        )

        user2 = UserRecord(
            user_id="test_user",
            generation=6,
            created_at=1234567890.0,
            updated_at=1234567900.0,
        )

        assert user2.generation > user1.generation
