$version: "2"

namespace layertwo.ffsync

// ============================================================================
// OIDC Discovery
// ============================================================================

@readonly
@http(method: "GET", uri: "/.well-known/openid-configuration")
@documentation("OpenID Connect discovery endpoint")
operation OIDCDiscovery {
    input: OIDCDiscoveryInput
    output: OIDCDiscoveryOutput
}

@input
structure OIDCDiscoveryInput {}

@output
structure OIDCDiscoveryOutput {
    @required
    issuer: String

    @required
    authorization_endpoint: String

    @required
    token_endpoint: String

    @required
    jwks_uri: String

    @required
    response_types_supported: StringList

    @required
    subject_types_supported: StringList

    @required
    id_token_signing_alg_values_supported: StringList
}

// ============================================================================
// JWKS
// ============================================================================

@readonly
@http(method: "GET", uri: "/v1/jwks")
@documentation("JSON Web Key Set endpoint for public signing keys")
operation JWKS {
    input: JWKSInput
    output: JWKSOutput
}

@input
structure JWKSInput {}

@output
structure JWKSOutput {
    @required
    @documentation("List of JSON Web Keys")
    keys: JWKList
}

list JWKList {
    member: JWKEntry
}

structure JWKEntry {
    @required
    kty: String

    @required
    kid: String

    @required
    use: String

    @required
    alg: String

    @required
    n: String

    @required
    e: String
}
