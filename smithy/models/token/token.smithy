$version: "2"

namespace layertwo.ffsync

use smithy.framework#ValidationException

@http(method: "POST", uri: "/1.0/sync/1.5")
@documentation("Exchange OIDC credentials for a Firefox Sync bearer token with HAWK credentials")
operation GetToken {
    input: GetTokenInput
    output: GetTokenOutput
    errors: [
        AuthenticationException
        ValidationException
    ]
}

@input
@documentation("Input for GetToken operation. The Authorization header with Bearer token is passed via API Gateway event headers and extracted by the Lambda function.")
structure GetTokenInput {}

@output
structure GetTokenOutput {
    @required
    @documentation("HAWK identifier for authentication")
    id: String

    @required
    @documentation("HAWK shared secret (64-character hexadecimal string)")
    key: String

    @required
    @documentation("Storage API endpoint URL (format: https://{base_url}/1.5/{user_id})")
    api_endpoint: String

    @required
    @documentation("Numeric user identifier (hash of user_id)")
    uid: Long

    @required
    @documentation("Token validity duration in seconds (always 300)")
    duration: Integer

    @required
    @documentation("Hash algorithm for HAWK authentication (always 'sha256')")
    hashalg: String
}
