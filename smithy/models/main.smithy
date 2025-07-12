$version: "2"

namespace layertwo.syncstorage

use aws.auth#sigv4
use aws.apigateway#integration
use aws.protocols#restJson1
use aws.apigateway#requestValidator
use aws.api#service
use smithy.framework#ValidationException
use aws.apigateway#mockIntegration

@restJson1
@documentation("SyncStorage")
@sigv4(name: "ffsync")
@mockIntegration(
    passThroughBehavior: "never"
    requestTemplates: {
        "application/json": "{\"statusCode\": 200}"
    }
    responses: {
        default: {
            statusCode: "200"
            responseTemplates: {
                "application/json": "{}"
            }
        }
    }
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
