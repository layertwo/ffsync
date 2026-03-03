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
def dynamodb_stubber(dynamodb_resource):
    with Stubber(dynamodb_resource.meta.client) as stubber:
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
def kms_client(boto_session):
    """KMS client from the test boto session."""
    return boto_session.client("kms")


@pytest.fixture
def kms_stubber(kms_client):
    """Botocore Stubber for KMS. Tests that call KMS add their own stubs."""
    stubber = Stubber(kms_client)
    stubber.activate()
    yield stubber
    stubber.deactivate()


@pytest.fixture
def apigw_client(boto_session):
    """API Gateway Management API client for WebSocket connection posting."""
    return boto_session.client(
        "apigatewaymanagementapi",
        endpoint_url="https://test.execute-api.us-east-1.amazonaws.com/prod",
    )


@pytest.fixture
def apigw_stubber(apigw_client):
    """Botocore Stubber for API Gateway Management API."""
    stubber = Stubber(apigw_client)
    stubber.activate()
    yield stubber
    stubber.deactivate()


@pytest.fixture(autouse=True)
def boto_session(aws_region_name, aws_access_key_id, aws_secret_access_key, aws_session_token):
    return boto3.session.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        aws_session_token=aws_session_token,
        region_name=aws_region_name,
    )


@pytest.fixture
def boto_session_patch(boto_session):
    with (
        patch("boto3.Session", autospec=True) as m,
        patch("boto3.session.Session", autospec=True) as m2,
    ):
        m.return_value = boto_session
        m2.return_value = boto_session
        yield m


@pytest.fixture(autouse=True)
def boto_resource_patch(
    boto_session, boto_session_patch, dynamodb_client, dynamodb_resource, kms_client, apigw_client
) -> Generator:
    def client(service, *args, **kwargs):
        if service == "dynamodb":
            return dynamodb_client
        if service == "kms":
            return kms_client
        if service == "apigatewaymanagementapi":
            return apigw_client

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
