"""Unit tests for DeviceManager with DynamoDB stubber"""

from unittest.mock import ANY, patch

import pytest

from src.services.device_manager import DeviceManager


class TestDeviceManager:
    """Test DeviceManager DynamoDB operations"""

    @pytest.fixture
    def manager(self, dynamodb_table):
        """Create DeviceManager instance with stubbed table"""
        return DeviceManager(table=dynamodb_table)

    @pytest.fixture
    def sample_uid(self):
        return "abcdef1234567890abcdef1234567890"

    @pytest.fixture
    def sample_session_token_id(self):
        return "session-token-id-abc123"

    @pytest.fixture
    def mock_time(self):
        """Mock time.time() for device_manager"""
        with patch("src.services.device_manager.time") as mock:
            mock.time.return_value = 1000000.0
            yield mock

    @pytest.fixture
    def mock_uuid(self):
        """Mock uuid.uuid4() for device_manager"""
        with patch("src.services.device_manager.uuid") as mock:
            mock_uuid4 = mock.uuid4.return_value
            mock_uuid4.hex = "aabbccdd11223344aabbccdd11223344"
            yield mock

    # -- upsert_device (create) ------------------------------------------------

    def test_upsert_device_creates_new(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_session_token_id,
        mock_time,
        mock_uuid,
    ):
        """upsert_device without id generates UUID and stores new device"""
        generated_id = "aabbccdd11223344aabbccdd11223344"

        # Stub put_item for the new device
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"DEVICE#{sample_uid}#{generated_id}",
                    "id": generated_id,
                    "name": "My Phone",
                    "type": "mobile",
                    "pushCallback": None,
                    "pushPublicKey": None,
                    "pushAuthKey": None,
                    "pushEndpointExpired": False,
                    "availableCommands": {},
                    "sessionTokenId": sample_session_token_id,
                    "createdAt": 1000000000,
                    "lastAccessTime": 1000000000,
                },
            },
        )

        result = manager.upsert_device(
            uid=sample_uid,
            session_token_id=sample_session_token_id,
            data={"name": "My Phone", "type": "mobile"},
        )

        assert result["id"] == generated_id
        assert result["name"] == "My Phone"
        assert result["type"] == "mobile"
        assert result["createdAt"] == 1000000000
        assert result["lastAccessTime"] == 1000000000
        assert result["sessionTokenId"] == sample_session_token_id
        dynamodb_stubber.assert_no_pending_responses()

    # -- upsert_device (update) ------------------------------------------------

    def test_upsert_device_updates_existing(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
        sample_session_token_id,
        mock_time,
    ):
        """upsert_device with id merges fields into existing device"""
        device_id = "existing-device-id-00000000000000"

        # Stub get_item for the existing device
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"DEVICE#{sample_uid}#{device_id}"},
                    "id": {"S": device_id},
                    "name": {"S": "Old Name"},
                    "type": {"S": "desktop"},
                    "createdAt": {"N": "999000000"},
                    "lastAccessTime": {"N": "999000000"},
                    "sessionTokenId": {"S": "old-session-token"},
                },
            },
            {
                "TableName": storage_table_name,
                "Key": {"PK": f"DEVICE#{sample_uid}#{device_id}"},
            },
        )

        # Stub put_item for the updated device
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": storage_table_name,
                "Item": {
                    "PK": f"DEVICE#{sample_uid}#{device_id}",
                    "id": device_id,
                    "name": "New Name",
                    "type": "desktop",
                    "createdAt": 999000000,
                    "lastAccessTime": 1000000000,
                    "sessionTokenId": sample_session_token_id,
                },
            },
        )

        result = manager.upsert_device(
            uid=sample_uid,
            session_token_id=sample_session_token_id,
            data={"id": device_id, "name": "New Name"},
        )

        assert result["id"] == device_id
        assert result["name"] == "New Name"
        assert result["type"] == "desktop"
        assert result["createdAt"] == 999000000
        assert result["lastAccessTime"] == 1000000000
        assert result["sessionTokenId"] == sample_session_token_id
        dynamodb_stubber.assert_no_pending_responses()

    # -- get_devices -----------------------------------------------------------

    def test_get_devices_returns_all(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
    ):
        """get_devices returns all devices for a user"""
        device_id_1 = "device-1-00000000000000000000"
        device_id_2 = "device-2-00000000000000000000"

        # Stub scan
        dynamodb_stubber.add_response(
            "scan",
            {
                "Items": [
                    {
                        "PK": {"S": f"DEVICE#{sample_uid}#{device_id_1}"},
                        "id": {"S": device_id_1},
                        "name": {"S": "Phone"},
                        "lastAccessTime": {"N": "2000000000"},
                    },
                    {
                        "PK": {"S": f"DEVICE#{sample_uid}#{device_id_2}"},
                        "id": {"S": device_id_2},
                        "name": {"S": "Laptop"},
                        "lastAccessTime": {"N": "2000000000"},
                    },
                ],
            },
            {
                "TableName": storage_table_name,
                "FilterExpression": ANY,
            },
        )

        devices = manager.get_devices(uid=sample_uid)

        assert len(devices) == 2
        assert devices[0]["id"] == device_id_1
        assert devices[0]["name"] == "Phone"
        assert devices[1]["id"] == device_id_2
        assert devices[1]["name"] == "Laptop"
        # PK should be stripped
        assert "PK" not in devices[0]
        assert "PK" not in devices[1]
        dynamodb_stubber.assert_no_pending_responses()

    def test_get_devices_filters_idle(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
    ):
        """get_devices excludes devices with lastAccessTime below threshold"""
        device_id_active = "device-active-0000000000000000"
        device_id_idle = "device-idle-00000000000000000"

        # Stub scan returning both active and idle devices
        dynamodb_stubber.add_response(
            "scan",
            {
                "Items": [
                    {
                        "PK": {"S": f"DEVICE#{sample_uid}#{device_id_active}"},
                        "id": {"S": device_id_active},
                        "name": {"S": "Active Phone"},
                        "lastAccessTime": {"N": "2000000000"},
                    },
                    {
                        "PK": {"S": f"DEVICE#{sample_uid}#{device_id_idle}"},
                        "id": {"S": device_id_idle},
                        "name": {"S": "Idle Laptop"},
                        "lastAccessTime": {"N": "1000000000"},
                    },
                ],
            },
            {
                "TableName": storage_table_name,
                "FilterExpression": ANY,
            },
        )

        devices = manager.get_devices(uid=sample_uid, filter_idle_timestamp=1500000000)

        assert len(devices) == 1
        assert devices[0]["id"] == device_id_active
        assert devices[0]["name"] == "Active Phone"
        dynamodb_stubber.assert_no_pending_responses()

    def test_get_devices_empty(
        self,
        manager,
        dynamodb_stubber,
        storage_table_name,
        sample_uid,
    ):
        """get_devices returns empty list when scan returns no items"""
        # Stub scan returning no items
        dynamodb_stubber.add_response(
            "scan",
            {"Items": []},
            {
                "TableName": storage_table_name,
                "FilterExpression": ANY,
            },
        )

        devices = manager.get_devices(uid=sample_uid)

        assert devices == []
        dynamodb_stubber.assert_no_pending_responses()
