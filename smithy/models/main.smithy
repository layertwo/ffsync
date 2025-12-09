$version: "2"

namespace layertwo.ffsync

use aws.apigateway#integration
use aws.apigateway#requestValidator
use aws.protocols#restJson1
use smithy.framework#ValidationException

@restJson1
@documentation("Firefox Sync Storage Server")
@integration(
    type: "aws_proxy"
    uri: "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/CDK_LAMBDA_FUNCTION_ARN/invocations"
    httpMethod: "POST"
    credentials: "CDK_API_ROLE_ARN"
    timeoutInMillis: 29000
)
@requestValidator("full")
service StorageService {
    version: "1.0"
    resources: [
        Storage
    ]
    errors: [
        ValidationException
        ConflictException
        PreconditionFailedException
        RequestTooLargeException
        QuotaExceededException
        CollectionNotFoundException
        AuthenticationException
    ]
}

@restJson1
@documentation("Firefox Sync Token Server - Issues authentication tokens for accessing the Storage API")
@integration(
    type: "aws_proxy"
    uri: "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/CDK_LAMBDA_FUNCTION_ARN/invocations"
    httpMethod: "POST"
    credentials: "CDK_API_ROLE_ARN"
    timeoutInMillis: 29000
)
@requestValidator("full")
service TokenService {
    version: "1.0"
    operations: [
        RequestToken
    ]
    errors: [
        AuthenticationException
        ValidationException
    ]
}
