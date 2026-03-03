"""Tests for Channel API lambda entrypoint"""

from unittest.mock import MagicMock

from src.entrypoint import channel_api_handler
from src.services.channel_service import ChannelService


class TestChannelApiHandler:
    def test_delegates_to_channel_service(self, sample_lambda_context):
        """Handler delegates to channel_service.handle."""
        mock_channel = MagicMock(spec=ChannelService)
        mock_channel.handle.return_value = {"statusCode": 200}

        mock_sp = MagicMock()
        mock_sp.channel_service = mock_channel

        event = {
            "requestContext": {
                "routeKey": "$connect",
                "connectionId": "conn-1",
                "domainName": "ws.example.com",
                "stage": "prod",
            },
        }

        result = channel_api_handler(event, sample_lambda_context, mock_sp)

        assert result == {"statusCode": 200}
        mock_channel.handle.assert_called_once_with(event, sample_lambda_context)


class TestServiceProviderChannelProperties:
    """Tests for ServiceProvider channel property initialization"""

    def test_channel_table_name_from_env(self, mock_service_provider):
        """Test channel_table_name reads from environment."""
        assert mock_service_provider.channel_table_name == "test-channel-table"

    def test_channel_table_creates_table_resource(self, mock_service_provider):
        """Test channel_table returns a DynamoDB Table resource."""
        table = mock_service_provider.channel_table
        assert table is not None

    def test_channel_service_creates_instance(self, mock_service_provider):
        """Test channel_service property creates ChannelService."""
        service = mock_service_provider.channel_service
        assert isinstance(service, ChannelService)
