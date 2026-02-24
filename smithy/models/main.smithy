$version: "2"

namespace layertwo.ffsync

use aws.apigateway#authorizer
use aws.apigateway#authorizers
use aws.apigateway#apiKeySource
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
@apiKeySource("AUTHORIZER")
@httpApiKeyAuth(name: "Authorization", in: "header")
@authorizer("hawk-authorizer")
@authorizers(
    "hawk-authorizer": {
        scheme: httpApiKeyAuth,
        type: "request"
        uri: "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/CDK_AUTH_LAMBDA_FUNCTION_ARN/invocations"
        credentials: "CDK_API_ROLE_ARN"
        identitySource: "method.request.header.Authorization",
        resultTtlInSeconds: 300
    }
)
service StorageService {
    version: "1.0"
    resources: [
        Storage
        RootStorage
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

@cors(
    origin: "CDK_CORS_ORIGIN"
    additionalAllowedHeaders: ["Authorization", "Content-Type", "X-Client-State"]
)
@restJson1
@documentation("Firefox Sync Auth Server - FxA-compatible authentication and token issuance")
@integration(
    type: "aws_proxy"
    uri: "arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/CDK_LAMBDA_FUNCTION_ARN/invocations"
    httpMethod: "POST"
    credentials: "CDK_API_ROLE_ARN"
    timeoutInMillis: 29000
)
@requestValidator("full")
service AuthService {
    version: "1.0"
    resources: [
        Account
        Session
        OAuth
    ]
    operations: [
        GetToken
        OIDCDiscovery
        JWKS
    ]
    errors: [
        AuthenticationException
        ValidationException
    ]
}
