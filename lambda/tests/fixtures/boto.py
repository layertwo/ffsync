"""AWS service fixtures with botocore stubbing"""

from typing import TYPE_CHECKING, Any, Generator, cast
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.stub import Stubber

if TYPE_CHECKING:
    from types_boto3_apigatewaymanagementapi.client import ApiGatewayManagementApiClient
    from types_boto3_dynamodb.client import DynamoDBClient
    from types_boto3_dynamodb.service_resource import DynamoDBServiceResource, Table
    from types_boto3_kms.client import KMSClient


@pytest.fixture(scope="session")
def aws_region_name() -> str:
    return "us-east-1"


@pytest.fixture(scope="session")
def aws_account_id() -> str:
    return "00000000000"


@pytest.fixture(scope="session")
def aws_access_key_id() -> str:
    return "fake-access-key-id"


@pytest.fixture(scope="session")
def aws_secret_access_key() -> str:
    return "fake-secret-access-key"


@pytest.fixture(scope="session")
def aws_session_token() -> str:
    return "fake-session-token"


@pytest.fixture
def dynamodb_client(boto_session: boto3.session.Session) -> DynamoDBClient:
    return boto_session.client("dynamodb")


@pytest.fixture
def dynamodb_resource(boto_session: boto3.session.Session) -> "DynamoDBServiceResource":
    return boto_session.resource("dynamodb")


@pytest.fixture
def dynamodb_stubber(
    dynamodb_resource: "DynamoDBServiceResource",
) -> Generator[Stubber, None, None]:
    with Stubber(dynamodb_resource.meta.client) as stubber:
        yield stubber


@pytest.fixture
def dynamodb_table(
    boto_session: boto3.session.Session, dynamodb_stubber: Stubber, storage_table_name: str
) -> "Table":
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
    table.meta.client = cast("DynamoDBClient", dynamodb_stubber.client)

    return table


@pytest.fixture
def kms_client(boto_session: boto3.session.Session) -> KMSClient:
    """KMS client from the test boto session."""
    return boto_session.client("kms")


@pytest.fixture
def kms_stubber(kms_client: KMSClient) -> Generator[Stubber, None, None]:
    """Botocore Stubber for KMS. Tests that call KMS add their own stubs."""
    with Stubber(kms_client) as stubber:
        yield stubber


@pytest.fixture
def apigw_client(boto_session: boto3.session.Session) -> ApiGatewayManagementApiClient:
    """API Gateway Management API client for WebSocket connection posting."""
    return boto_session.client(
        "apigatewaymanagementapi",
        endpoint_url="https://test.execute-api.us-east-1.amazonaws.com/prod",
    )


@pytest.fixture
def apigw_stubber(apigw_client: ApiGatewayManagementApiClient) -> Generator[Stubber, None, None]:
    """Botocore Stubber for API Gateway Management API."""
    with Stubber(apigw_client) as stubber:
        yield stubber


@pytest.fixture(autouse=True)
def boto_session(
    aws_region_name: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
    aws_session_token: str,
) -> boto3.session.Session:
    return boto3.session.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        aws_session_token=aws_session_token,
        region_name=aws_region_name,
    )


@pytest.fixture
def boto_session_patch(boto_session: boto3.session.Session) -> Generator[MagicMock, None, None]:
    with (
        patch("boto3.Session", autospec=True) as m,
        patch("boto3.session.Session", autospec=True) as m2,
    ):
        m.return_value = boto_session
        m2.return_value = boto_session
        yield m


@pytest.fixture(autouse=True)
def boto_resource_patch(
    boto_session: boto3.session.Session,
    boto_session_patch: MagicMock,
    dynamodb_client: DynamoDBClient,
    dynamodb_resource: "DynamoDBServiceResource",
    kms_client: KMSClient,
    apigw_client: ApiGatewayManagementApiClient,
) -> Generator:
    def client(service: str, *args: Any, **kwargs: Any) -> Any:
        if service == "dynamodb":
            return dynamodb_client
        if service == "kms":
            return kms_client
        if service == "apigatewaymanagementapi":
            return apigw_client

        raise ValueError(f"client for {service} not recognized")

    def resource(service: str, *args: Any, **kwargs: Any) -> Any:
        if service == "dynamodb":
            return dynamodb_resource

        raise ValueError(f"resource for {service} not recognized")

    with (
        patch.object(boto_session, "resource", resource),
        patch.object(boto_session, "client", client) as m2,
    ):
        yield m2
