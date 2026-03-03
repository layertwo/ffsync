"""Channel Service — WebSocket message relay for device pairing."""

import json
import time
import uuid

from botocore.exceptions import ClientError

MAX_CONNECTIONS_PER_CHANNEL = 3
MAX_MESSAGES_PER_CHANNEL = 10
CHANNEL_TTL_SECONDS = 300


class ChannelService:
    """WebSocket channel relay for device pairing.

    Uses a PK-only DynamoDB table with TTL:
    - CHANNEL#{channelId} — connections (list), messageCount, expiry
    - CONN#{connectionId} — channelId, expiry
    """

    def __init__(self, table, session):
        self._table = table
        self._session = session
        self._apigw_clients = {}

    def handle(self, event, context):
        """Dispatch on WebSocket route key."""
        route_key = event["requestContext"]["routeKey"]
        connection_id = event["requestContext"]["connectionId"]

        if route_key == "$connect":
            return self._handle_connect(event, connection_id)
        elif route_key == "$disconnect":
            self._handle_disconnect(connection_id)
            return {"statusCode": 200}
        elif route_key == "$default":
            return self._handle_message(event, connection_id)
        else:
            return {"statusCode": 400, "body": "Unknown route"}

    def _handle_connect(self, event, connection_id):
        """Handle $connect — create or join a channel."""
        params = event.get("queryStringParameters") or {}
        channel_id = params.get("channelId")
        expiry = int(time.time()) + CHANNEL_TTL_SECONDS

        if channel_id:
            return self._join_channel(channel_id, connection_id, expiry)
        else:
            return self._create_channel(event, connection_id, expiry)

    def _create_channel(self, event, connection_id, expiry):
        """Create a new channel with this connection as the first member."""
        channel_id = str(uuid.uuid4())

        # Put channel metadata
        self._table.put_item(
            Item={
                "PK": f"CHANNEL#{channel_id}",
                "connections": [connection_id],
                "messageCount": 0,
                "expiry": expiry,
            }
        )

        # Put reverse lookup
        self._table.put_item(
            Item={
                "PK": f"CONN#{connection_id}",
                "channelId": channel_id,
                "expiry": expiry,
            }
        )

        # Notify creator of channel ID
        self._post_to_connection(
            event,
            connection_id,
            json.dumps({"channelId": channel_id}),
        )

        return {"statusCode": 200}

    def _join_channel(self, channel_id, connection_id, expiry):
        """Join an existing channel atomically."""
        try:
            self._table.update_item(
                Key={"PK": f"CHANNEL#{channel_id}"},
                UpdateExpression="SET connections = list_append(connections, :conn)",
                ConditionExpression="attribute_exists(PK) AND size(connections) < :max",
                ExpressionAttributeValues={
                    ":conn": [connection_id],
                    ":max": MAX_CONNECTIONS_PER_CHANNEL,
                },
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # Distinguish 404 (channel doesn't exist) vs 403 (channel full)
                result = self._table.get_item(Key={"PK": f"CHANNEL#{channel_id}"})
                if "Item" not in result:
                    return {"statusCode": 404, "body": "Channel not found"}
                else:
                    return {"statusCode": 403, "body": "Channel full"}
            raise

        # Put reverse lookup
        self._table.put_item(
            Item={
                "PK": f"CONN#{connection_id}",
                "channelId": channel_id,
                "expiry": expiry,
            }
        )

        return {"statusCode": 200}

    def _handle_disconnect(self, connection_id):
        """Handle disconnect — remove connection from channel."""
        # Delete reverse lookup first (idempotent guard against double-disconnect)
        result = self._table.get_item(Key={"PK": f"CONN#{connection_id}"})
        if "Item" not in result:
            return

        channel_id = result["Item"]["channelId"]
        self._table.delete_item(Key={"PK": f"CONN#{connection_id}"})

        # Get channel to find connection index
        channel_result = self._table.get_item(Key={"PK": f"CHANNEL#{channel_id}"})
        if "Item" not in channel_result:
            return

        connections = channel_result["Item"]["connections"]
        if connection_id in connections:
            index = connections.index(connection_id)
            self._table.update_item(
                Key={"PK": f"CHANNEL#{channel_id}"},
                UpdateExpression=f"REMOVE connections[{index}]",
            )

    def _handle_message(self, event, connection_id):
        """Handle incoming message — relay to other connections."""
        # Look up channel for this connection
        result = self._table.get_item(Key={"PK": f"CONN#{connection_id}"})
        if "Item" not in result:
            return {"statusCode": 404, "body": "Connection not found"}

        channel_id = result["Item"]["channelId"]

        # Atomic message count increment with limit check
        try:
            self._table.update_item(
                Key={"PK": f"CHANNEL#{channel_id}"},
                UpdateExpression="SET messageCount = messageCount + :one",
                ConditionExpression=("attribute_exists(PK) AND messageCount < :max"),
                ExpressionAttributeValues={
                    ":one": 1,
                    ":max": MAX_MESSAGES_PER_CHANNEL,
                },
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # Distinguish 404 vs 429
                channel_result = self._table.get_item(Key={"PK": f"CHANNEL#{channel_id}"})
                if "Item" not in channel_result:
                    return {"statusCode": 404, "body": "Channel not found"}
                else:
                    return {"statusCode": 429, "body": "Message limit reached"}
            raise

        # Get connections from channel metadata
        channel_result = self._table.get_item(Key={"PK": f"CHANNEL#{channel_id}"})
        if "Item" not in channel_result:
            return {"statusCode": 404, "body": "Channel not found"}

        connections = channel_result["Item"]["connections"]
        message_body = event.get("body", "")

        self._relay_message(event, connection_id, connections, message_body)

        return {"statusCode": 200}

    def _relay_message(self, event, sender_connection_id, connections, message_body):
        """Relay message to all connections except sender."""
        data = json.dumps(
            {
                "sender": sender_connection_id,
                "body": message_body,
            }
        )
        for conn_id in connections:
            if conn_id != sender_connection_id:
                self._post_to_connection(event, conn_id, data)

    def _post_to_connection(self, event, connection_id, data):
        """Post data to a WebSocket connection via API Gateway Management API."""
        client = self._get_apigw_client(event)
        try:
            client.post_to_connection(
                ConnectionId=connection_id,
                Data=data.encode("utf-8") if isinstance(data, str) else data,
            )
        except client.exceptions.GoneException:
            self._handle_disconnect(connection_id)

    def _get_apigw_client(self, event):
        """Lazy API Gateway Management API client, cached by endpoint.

        Uses the execute-api domain (not the custom domain) because the
        Management API and its IAM policy are scoped to the execute-api ARN.
        """
        api_id = event["requestContext"]["apiId"]
        stage = event["requestContext"]["stage"]
        region = self._session.region_name
        endpoint = f"https://{api_id}.execute-api.{region}.amazonaws.com/{stage}"

        if endpoint not in self._apigw_clients:
            self._apigw_clients[endpoint] = self._session.client(
                "apigatewaymanagementapi",
                endpoint_url=endpoint,
            )

        return self._apigw_clients[endpoint]
