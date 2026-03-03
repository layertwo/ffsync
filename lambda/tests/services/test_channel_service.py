"""Unit tests for ChannelService with DynamoDB stubber"""

import json
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from src.services.channel_service import (
    CHANNEL_TTL_SECONDS,
    MAX_CONNECTIONS_PER_CHANNEL,
    MAX_MESSAGES_PER_CHANNEL,
    ChannelService,
)

CHANNEL_TABLE_NAME = "test-channel-table"
FIXED_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FIXED_TIME = 1700000000


def _ws_event(route_key="$default", connection_id="conn-1", body=None, query_params=None):
    """Build a WebSocket API Gateway event dict."""
    event = {
        "requestContext": {
            "routeKey": route_key,
            "connectionId": connection_id,
            "apiId": "testapi123",
            "domainName": "ws.example.com",
            "stage": "prod",
        },
        "body": body,
        "queryStringParameters": query_params,
    }
    return event


class TestChannelService:
    """Test ChannelService DynamoDB operations"""

    @pytest.fixture
    def channel_table(self, boto_session, dynamodb_stubber):
        resource = boto_session.resource("dynamodb")
        table = resource.Table(CHANNEL_TABLE_NAME)
        table.meta.client = dynamodb_stubber.client
        return table

    @pytest.fixture
    def service(self, channel_table, boto_session, apigw_client, apigw_stubber):
        svc = ChannelService(table=channel_table, session=boto_session)
        # Pre-populate the APIGW client cache with the shared stubbed client.
        # The key must match what _get_apigw_client computes from _ws_event():
        # f"https://{apiId}.execute-api.{region}.amazonaws.com/{stage}"
        svc._apigw_clients["https://testapi123.execute-api.us-east-1.amazonaws.com/prod"] = (
            apigw_client
        )
        return svc

    # -- Constants ------------------------------------------------------------

    def test_constants(self):
        assert MAX_CONNECTIONS_PER_CHANNEL == 3
        assert MAX_MESSAGES_PER_CHANNEL == 10
        assert CHANNEL_TTL_SECONDS == 300

    # -- Create channel -------------------------------------------------------

    @patch("src.services.channel_service.uuid.uuid4", return_value=FIXED_UUID)
    @patch("src.services.channel_service.time.time", return_value=FIXED_TIME)
    def test_create_channel(
        self,
        mock_time,
        mock_uuid,
        service,
        dynamodb_stubber,
        apigw_stubber,
    ):
        """Create channel stores metadata + reverse lookup + sends channelId."""
        expiry = FIXED_TIME + CHANNEL_TTL_SECONDS

        # put_item for CHANNEL# metadata
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Item": {
                    "PK": f"CHANNEL#{FIXED_UUID}",
                    "connections": ["conn-1"],
                    "messageCount": 0,
                    "expiry": expiry,
                },
            },
        )

        # put_item for CONN# reverse lookup
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Item": {
                    "PK": "CONN#conn-1",
                    "channelId": FIXED_UUID,
                    "expiry": expiry,
                },
            },
        )

        # post_to_connection to notify creator of channelId
        apigw_stubber.add_response(
            "post_to_connection",
            {},
            {
                "ConnectionId": "conn-1",
                "Data": json.dumps({"channelId": FIXED_UUID}).encode("utf-8"),
            },
        )

        event = _ws_event(route_key="$connect", connection_id="conn-1")
        result = service.handle(event, None)

        assert result == {"statusCode": 200}
        apigw_stubber.assert_no_pending_responses()

    # -- Join channel ---------------------------------------------------------

    @patch("src.services.channel_service.time.time", return_value=FIXED_TIME)
    def test_join_channel(
        self,
        mock_time,
        service,
        dynamodb_stubber,
    ):
        """Join existing channel via atomic update_item + reverse lookup."""
        expiry = FIXED_TIME + CHANNEL_TTL_SECONDS
        channel_id = "existing-channel"

        # update_item for atomic join
        dynamodb_stubber.add_response("update_item", {}, None)

        # put_item for CONN# reverse lookup
        dynamodb_stubber.add_response(
            "put_item",
            {},
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Item": {
                    "PK": "CONN#conn-2",
                    "channelId": channel_id,
                    "expiry": expiry,
                },
            },
        )

        event = _ws_event(
            route_key="$connect",
            connection_id="conn-2",
            query_params={"channelId": channel_id},
        )
        result = service.handle(event, None)

        assert result == {"statusCode": 200}

    # -- Join nonexistent channel ---------------------------------------------

    def test_join_nonexistent_channel_returns_404(
        self,
        service,
        dynamodb_stubber,
    ):
        """ConditionalCheckFailed + empty get_item => 404."""
        channel_id = "no-such-channel"

        # update_item fails with ConditionalCheckFailedException
        dynamodb_stubber.add_client_error(
            "update_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="Condition not met",
        )

        # get_item to distinguish 404 vs 403 => empty
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": f"CHANNEL#{channel_id}"},
            },
        )

        event = _ws_event(
            route_key="$connect",
            connection_id="conn-2",
            query_params={"channelId": channel_id},
        )
        result = service.handle(event, None)

        assert result == {"statusCode": 404, "body": "Channel not found"}

    # -- Join full channel ----------------------------------------------------

    def test_join_full_channel_returns_403(
        self,
        service,
        dynamodb_stubber,
    ):
        """ConditionalCheckFailed + channel exists => 403."""
        channel_id = "full-channel"

        # update_item fails with ConditionalCheckFailedException
        dynamodb_stubber.add_client_error(
            "update_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="Condition not met",
        )

        # get_item returns existing channel (full)
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"CHANNEL#{channel_id}"},
                    "connections": {"L": [{"S": "c1"}, {"S": "c2"}, {"S": "c3"}]},
                    "messageCount": {"N": "0"},
                    "expiry": {"N": str(FIXED_TIME + CHANNEL_TTL_SECONDS)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": f"CHANNEL#{channel_id}"},
            },
        )

        event = _ws_event(
            route_key="$connect",
            connection_id="conn-4",
            query_params={"channelId": channel_id},
        )
        result = service.handle(event, None)

        assert result == {"statusCode": 403, "body": "Channel full"}

    # -- Disconnect with cleanup ----------------------------------------------

    def test_disconnect_cleans_up(
        self,
        service,
        dynamodb_stubber,
    ):
        """Disconnect removes reverse lookup then patches connections list."""
        channel_id = "chan-1"

        # get_item for CONN#
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "CONN#conn-1"},
                    "channelId": {"S": channel_id},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-1"},
            },
        )

        # delete_item for CONN#
        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-1"},
            },
        )

        # get_item for CHANNEL#
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"CHANNEL#{channel_id}"},
                    "connections": {"L": [{"S": "conn-1"}, {"S": "conn-2"}]},
                    "messageCount": {"N": "0"},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": f"CHANNEL#{channel_id}"},
            },
        )

        # update_item to REMOVE connections[0]
        dynamodb_stubber.add_response("update_item", {}, None)

        event = _ws_event(route_key="$disconnect", connection_id="conn-1")
        result = service.handle(event, None)

        assert result == {"statusCode": 200}

    # -- Disconnect unknown connection ----------------------------------------

    def test_disconnect_unknown_connection(
        self,
        service,
        dynamodb_stubber,
    ):
        """Disconnect with no reverse lookup => no-op."""
        # get_item for CONN# => empty
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#unknown"},
            },
        )

        event = _ws_event(route_key="$disconnect", connection_id="unknown")
        result = service.handle(event, None)

        assert result == {"statusCode": 200}

    # -- Relay message --------------------------------------------------------

    def test_relay_message(
        self,
        service,
        dynamodb_stubber,
        apigw_stubber,
    ):
        """Message relayed to other connections in the channel."""
        channel_id = "chan-1"

        # get_item for CONN#
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "CONN#conn-1"},
                    "channelId": {"S": channel_id},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-1"},
            },
        )

        # update_item for atomic message count increment
        dynamodb_stubber.add_response("update_item", {}, None)

        # get_item for CHANNEL# (connections)
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"CHANNEL#{channel_id}"},
                    "connections": {"L": [{"S": "conn-1"}, {"S": "conn-2"}]},
                    "messageCount": {"N": "1"},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": f"CHANNEL#{channel_id}"},
            },
        )

        # post_to_connection to relay message to conn-2
        apigw_stubber.add_response(
            "post_to_connection",
            {},
            {
                "ConnectionId": "conn-2",
                "Data": json.dumps({"sender": "conn-1", "body": "hello"}).encode("utf-8"),
            },
        )

        event = _ws_event(
            route_key="$default",
            connection_id="conn-1",
            body="hello",
        )
        result = service.handle(event, None)

        assert result == {"statusCode": 200}
        apigw_stubber.assert_no_pending_responses()

    # -- Unknown connection message -------------------------------------------

    def test_unknown_connection_message_returns_404(
        self,
        service,
        dynamodb_stubber,
    ):
        """Message from unknown connection => 404."""
        # get_item for CONN# => empty
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-x"},
            },
        )

        event = _ws_event(route_key="$default", connection_id="conn-x", body="hi")
        result = service.handle(event, None)

        assert result == {"statusCode": 404, "body": "Connection not found"}

    # -- Channel not found on message -----------------------------------------

    def test_channel_not_found_on_message_returns_404(
        self,
        service,
        dynamodb_stubber,
    ):
        """Message with valid connection but missing channel => 404."""
        channel_id = "gone-channel"

        # get_item for CONN#
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "CONN#conn-1"},
                    "channelId": {"S": channel_id},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-1"},
            },
        )

        # update_item fails (channel deleted)
        dynamodb_stubber.add_client_error(
            "update_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="Condition not met",
        )

        # get_item for CHANNEL# => empty (channel gone)
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": f"CHANNEL#{channel_id}"},
            },
        )

        event = _ws_event(route_key="$default", connection_id="conn-1", body="hi")
        result = service.handle(event, None)

        assert result == {"statusCode": 404, "body": "Channel not found"}

    # -- Message limit --------------------------------------------------------

    def test_message_limit_returns_429(
        self,
        service,
        dynamodb_stubber,
    ):
        """Message count at limit => 429."""
        channel_id = "busy-channel"

        # get_item for CONN#
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "CONN#conn-1"},
                    "channelId": {"S": channel_id},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-1"},
            },
        )

        # update_item fails (message count at limit)
        dynamodb_stubber.add_client_error(
            "update_item",
            service_error_code="ConditionalCheckFailedException",
            service_message="Condition not met",
        )

        # get_item for CHANNEL# => exists (so it's a 429, not 404)
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"CHANNEL#{channel_id}"},
                    "connections": {"L": [{"S": "conn-1"}]},
                    "messageCount": {"N": "10"},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": f"CHANNEL#{channel_id}"},
            },
        )

        event = _ws_event(route_key="$default", connection_id="conn-1", body="hi")
        result = service.handle(event, None)

        assert result == {"statusCode": 429, "body": "Message limit reached"}

    # -- GoneException triggers cleanup ---------------------------------------

    def test_gone_exception_triggers_cleanup(
        self,
        service,
        dynamodb_stubber,
        apigw_stubber,
    ):
        """When post_to_connection raises GoneException, stale conn is cleaned up."""
        channel_id = "chan-1"

        # get_item for CONN# (sender)
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "CONN#conn-1"},
                    "channelId": {"S": channel_id},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-1"},
            },
        )

        # update_item for message count
        dynamodb_stubber.add_response("update_item", {}, None)

        # get_item for CHANNEL# (connections)
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"CHANNEL#{channel_id}"},
                    "connections": {"L": [{"S": "conn-1"}, {"S": "conn-stale"}]},
                    "messageCount": {"N": "1"},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": f"CHANNEL#{channel_id}"},
            },
        )

        # post_to_connection raises GoneException for stale conn
        apigw_stubber.add_client_error(
            "post_to_connection",
            service_error_code="GoneException",
            service_message="Connection gone",
            expected_params={
                "ConnectionId": "conn-stale",
                "Data": json.dumps({"sender": "conn-1", "body": "ping"}).encode("utf-8"),
            },
        )

        # _handle_disconnect cleanup stubs for the stale connection:
        # get_item for CONN#conn-stale
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "CONN#conn-stale"},
                    "channelId": {"S": channel_id},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-stale"},
            },
        )

        # delete_item for CONN#conn-stale
        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-stale"},
            },
        )

        # get_item for CHANNEL# to find index
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"CHANNEL#{channel_id}"},
                    "connections": {"L": [{"S": "conn-1"}, {"S": "conn-stale"}]},
                    "messageCount": {"N": "1"},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": f"CHANNEL#{channel_id}"},
            },
        )

        # update_item to REMOVE connections[1]
        dynamodb_stubber.add_response("update_item", {}, None)

        event = _ws_event(route_key="$default", connection_id="conn-1", body="ping")
        result = service.handle(event, None)

        assert result == {"statusCode": 200}
        apigw_stubber.assert_no_pending_responses()

    # -- Empty body relay -----------------------------------------------------

    def test_empty_body_relay(
        self,
        service,
        dynamodb_stubber,
        apigw_stubber,
    ):
        """Relay works when body is missing from event."""
        channel_id = "chan-1"

        # get_item for CONN#
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "CONN#conn-1"},
                    "channelId": {"S": channel_id},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-1"},
            },
        )

        # update_item for message count
        dynamodb_stubber.add_response("update_item", {}, None)

        # get_item for CHANNEL# (connections)
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"CHANNEL#{channel_id}"},
                    "connections": {"L": [{"S": "conn-1"}, {"S": "conn-2"}]},
                    "messageCount": {"N": "1"},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": f"CHANNEL#{channel_id}"},
            },
        )

        # post_to_connection to relay message to conn-2 (empty body)
        apigw_stubber.add_response(
            "post_to_connection",
            {},
            {
                "ConnectionId": "conn-2",
                "Data": json.dumps({"sender": "conn-1", "body": ""}).encode("utf-8"),
            },
        )

        # Event with no body key
        event = _ws_event(route_key="$default", connection_id="conn-1")
        del event["body"]
        result = service.handle(event, None)

        assert result == {"statusCode": 200}
        apigw_stubber.assert_no_pending_responses()

    # -- Lazy APIGW client init -----------------------------------------------

    def test_lazy_apigw_client_init(
        self,
        channel_table,
        boto_session,
    ):
        """Client is created lazily on first use and cached by endpoint."""
        svc = ChannelService(table=channel_table, session=boto_session)
        assert svc._apigw_clients == {}

        event = _ws_event()
        client1 = svc._get_apigw_client(event)
        expected_key = "https://testapi123.execute-api.us-east-1.amazonaws.com/prod"
        assert expected_key in svc._apigw_clients
        assert client1 is svc._apigw_clients[expected_key]

        # Second call returns the same cached client
        client2 = svc._get_apigw_client(event)
        assert client1 is client2

    # -- Disconnect: channel gone after CONN delete ----------------------------

    def test_disconnect_channel_gone_after_conn_delete(
        self,
        service,
        dynamodb_stubber,
    ):
        """Disconnect when channel disappears between CONN delete and channel lookup."""
        channel_id = "vanished-chan"

        # get_item for CONN#
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "CONN#conn-1"},
                    "channelId": {"S": channel_id},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-1"},
            },
        )

        # delete_item for CONN#
        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-1"},
            },
        )

        # get_item for CHANNEL# => empty (channel gone)
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": f"CHANNEL#{channel_id}"},
            },
        )

        event = _ws_event(route_key="$disconnect", connection_id="conn-1")
        result = service.handle(event, None)

        assert result == {"statusCode": 200}

    # -- Disconnect: connection not in connections list -----------------------

    def test_disconnect_connection_not_in_list(
        self,
        service,
        dynamodb_stubber,
    ):
        """Disconnect when connection is not in the channel's connections list."""
        channel_id = "chan-1"

        # get_item for CONN#
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "CONN#conn-1"},
                    "channelId": {"S": channel_id},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-1"},
            },
        )

        # delete_item for CONN#
        dynamodb_stubber.add_response(
            "delete_item",
            {},
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-1"},
            },
        )

        # get_item for CHANNEL# => connection already removed from list
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": f"CHANNEL#{channel_id}"},
                    "connections": {"L": [{"S": "conn-other"}]},
                    "messageCount": {"N": "0"},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": f"CHANNEL#{channel_id}"},
            },
        )

        event = _ws_event(route_key="$disconnect", connection_id="conn-1")
        result = service.handle(event, None)

        assert result == {"statusCode": 200}

    # -- Join: unexpected ClientError re-raised ------------------------------

    def test_join_unexpected_client_error_reraised(
        self,
        service,
        dynamodb_stubber,
    ):
        """Non-ConditionalCheckFailed ClientError is re-raised on join."""
        dynamodb_stubber.add_client_error(
            "update_item",
            service_error_code="InternalServerError",
            service_message="Unexpected error",
        )

        event = _ws_event(
            route_key="$connect",
            connection_id="conn-2",
            query_params={"channelId": "some-channel"},
        )
        with pytest.raises(ClientError):
            service.handle(event, None)

    # -- Message: unexpected ClientError re-raised ---------------------------

    def test_message_unexpected_client_error_reraised(
        self,
        service,
        dynamodb_stubber,
    ):
        """Non-ConditionalCheckFailed ClientError is re-raised on message."""
        channel_id = "chan-1"

        # get_item for CONN#
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "CONN#conn-1"},
                    "channelId": {"S": channel_id},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-1"},
            },
        )

        # update_item fails with unexpected error
        dynamodb_stubber.add_client_error(
            "update_item",
            service_error_code="InternalServerError",
            service_message="Unexpected error",
        )

        event = _ws_event(route_key="$default", connection_id="conn-1", body="hi")
        with pytest.raises(ClientError):
            service.handle(event, None)

    # -- Message: channel gone between count update and connections lookup ----

    def test_message_channel_gone_after_count_update(
        self,
        service,
        dynamodb_stubber,
    ):
        """Channel disappears between message count update and connections fetch."""
        channel_id = "ephemeral-chan"

        # get_item for CONN#
        dynamodb_stubber.add_response(
            "get_item",
            {
                "Item": {
                    "PK": {"S": "CONN#conn-1"},
                    "channelId": {"S": channel_id},
                    "expiry": {"N": str(FIXED_TIME)},
                }
            },
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": "CONN#conn-1"},
            },
        )

        # update_item for message count succeeds
        dynamodb_stubber.add_response("update_item", {}, None)

        # get_item for CHANNEL# => empty (TTL expired between calls)
        dynamodb_stubber.add_response(
            "get_item",
            {},
            {
                "TableName": CHANNEL_TABLE_NAME,
                "Key": {"PK": f"CHANNEL#{channel_id}"},
            },
        )

        event = _ws_event(route_key="$default", connection_id="conn-1", body="hi")
        result = service.handle(event, None)

        assert result == {"statusCode": 404, "body": "Channel not found"}

    # -- Unknown route --------------------------------------------------------

    def test_unknown_route_returns_400(self, service):
        """Unknown route key returns 400."""
        event = _ws_event(route_key="$unknown")
        result = service.handle(event, None)

        assert result == {"statusCode": 400, "body": "Unknown route"}
