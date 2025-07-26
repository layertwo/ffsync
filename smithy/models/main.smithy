$version: "2"

namespace layertwo.syncstorage

use aws.apigateway#mockIntegration
use aws.apigateway#requestValidator
use aws.auth#sigv4
use aws.protocols#restJson1
use smithy.framework#ValidationException

@restJson1
@documentation("SyncStorage")
@sigv4(name: "ffsync")
@mockIntegration(
    passThroughBehavior: "never"
    requestTemplates: { "application/json": "{\"statusCode\": 200}" }
    responses: {
        default: {
            statusCode: "200"
            responseTemplates: { "application/json": "{}" }
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
