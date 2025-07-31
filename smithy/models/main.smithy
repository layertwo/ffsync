$version: "2"

namespace layertwo.syncstorage

use aws.apigateway#integration
use aws.apigateway#requestValidator
use aws.auth#sigv4
use aws.protocols#restJson1
use smithy.framework#ValidationException

@restJson1
@documentation("SyncStorage")
@sigv4(name: "ffsync")
@integration(
    type: "aws_proxy",
    uri: "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/CDK_LAMBDA_FUNCTION_ARN/invocations"
    httpMethod: "POST"
    credentials: "CDK_API_ROLE_ARN",
    timeoutInMillis: 29000,
)
@requestValidator("full")
service StorageService {
    version: "1.5"
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
