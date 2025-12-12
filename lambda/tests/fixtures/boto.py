"""AWS service fixtures with botocore stubbing"""

from typing import Generator
from unittest.mock import patch

import boto3
import pytest
from botocore.stub import Stubber


@pytest.fixture(scope="session")
def aws_region_name():
    return "us-east-1"


@pytest.fixture(scope="session")
def aws_account_id():
    return "00000000000"


@pytest.fixture(scope="session")
def aws_access_key_id():
    return "fake-access-key-id"


@pytest.fixture(scope="session")
def aws_secret_access_key():
    return "fake-secret-access-key"


@pytest.fixture(scope="session")
def aws_session_token():
    return "fake-session-token"


@pytest.fixture
def dynamodb_client(boto_session):
    return boto_session.client("dynamodb")


@pytest.fixture
def dynamodb_resource(boto_session):
    return boto_session.resource("dynamodb")


@pytest.fixture
def dynamodb_stubber(dynamodb_client):
    with Stubber(dynamodb_client) as stubber:
        yield stubber


@pytest.fixture
def dynamodb_table(boto_session, dynamodb_stubber, storage_table_name):
    """
    Provides a DynamoDB Table resource with stubbed client.

    The Table resource's internal client is replaced with the stubbed client,
    allowing all Table operations to use mocked responses from dynamodb_stubber.

    Usage:
        def test_something(dynamodb_table, dynamodb_stubber):
            # Add stubbed responses
            dynamodb_stubber.add_response('get_item', {...})

            # Use the table with stubbed client
            response = dynamodb_table.get_item(Key={...})

    Args:
        boto_session: The test boto3.Session
        dynamodb_stubber: The stubbed DynamoDB client
        storage_table_name: The table name from environment

    Returns:
        DynamoDB Table resource with stubbed client
    """
    resource = boto_session.resource("dynamodb")
    table = resource.Table(storage_table_name)

    # Replace the Table's internal client with the stubbed one
    table.meta.client = dynamodb_stubber.client

    return table


@pytest.fixture
def secretsmanager_client(boto_session):
    """
    Provides a Secrets Manager client for stubbing.

    This client is created once and can be stubbed, then injected
    into the ServiceProvider via MockServiceProvider.
    """
    return boto_session.client("secretsmanager")


@pytest.fixture
def secretsmanager_stubber(secretsmanager_client):
    """
    Provides a Secrets Manager client with botocore Stubber for testing.

    Usage:
        def test_secrets(secretsmanager_stubber):
            secretsmanager_stubber.add_response(
                'get_secret_value',
                {'SecretString': '{"key": "value"}'},
                {'SecretId': 'my-secret-arn'}
            )
    """
    with Stubber(secretsmanager_client) as stubber:
        yield stubber


@pytest.fixture(autouse=True)
def boto_session(aws_region_name, aws_access_key_id, aws_secret_access_key, aws_session_token):
    # Load internal service models before creating a boto session
    return boto3.session.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        aws_session_token=aws_session_token,
        region_name=aws_region_name,
    )


@pytest.fixture
def boto_session_patch(boto_session):
    # Libraries are inconsistent about which is used
    with (
        patch("boto3.Session", autospec=True) as m,
        patch("boto3.session.Session", autospec=True) as m2,
    ):
        m.return_value = boto_session
        m2.return_value = boto_session
        yield m


@pytest.fixture(autouse=True)
def boto_resource_patch(
    boto_session, boto_session_patch, dynamodb_client, dynamodb_resource, secretsmanager_client
) -> Generator:
    def client(service, *args, **kwargs):
        if service == "dynamodb":
            return dynamodb_client
        if service == "secretsmanager":
            return secretsmanager_client

        raise ValueError(f"client for {service} not recognized")

    def resource(service, *args, **kwargs):
        if service == "dynamodb":
            return dynamodb_resource

        raise ValueError(f"resource for {service} not recognized")

    with (
        patch.object(boto_session, "resource", resource),
        patch.object(boto_session, "client", client) as m2,
    ):
        yield m2
