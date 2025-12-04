"""AWS service fixtures with botocore stubbing"""

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


@pytest.fixture(autouse=True)
def boto_session(
    aws_region_name, aws_access_key_id, aws_secret_access_key, aws_session_token
):
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
    with patch("boto3.Session", autospec=True) as m, patch(
        "boto3.session.Session", autospec=True
    ) as m2:
        m.return_value = boto_session
        m2.return_value = boto_session
        yield m


@pytest.fixture
def dynamodb_stubber(boto_session):
    """
    Provides a DynamoDB client with botocore Stubber for testing AWS operations.
    Uses the unified boto_session fixture.

    Usage:
        def test_dynamodb_operation(dynamodb_stubber):
            # Add expected responses
            dynamodb_stubber.add_response(
                'get_item',
                {'Item': {'id': {'S': 'test-id'}, 'data': {'S': 'test-data'}}},
                {'TableName': 'test-table', 'Key': {'id': {'S': 'test-id'}}}
            )

            # Use the stubbed client
            response = dynamodb_stubber.client.get_item(
                TableName='test-table',
                Key={'id': {'S': 'test-id'}}
            )

    Args:
        mock_aws_session: The unified AWS session fixture

    Yields:
        botocore.stub.Stubber: Activated stubber for DynamoDB client
    """
    with Stubber(boto_session.client("dynamodb")) as stubber:
        yield stubber
