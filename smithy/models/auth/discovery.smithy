$version: "2"

namespace layertwo.ffsync

use smithy.framework#ValidationException

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

// ============================================================================
// OIDC Provider Config (proxy for frontend)
// ============================================================================

@readonly
@http(method: "GET", uri: "/v1/oidc/config")
@documentation("Returns the external OIDC provider's authorization endpoint for redirect-based auth flows")
operation OIDCProviderConfig {
    input: OIDCProviderConfigInput
    output: OIDCProviderConfigOutput
}

@input
structure OIDCProviderConfigInput {}

@output
structure OIDCProviderConfigOutput {
    @required
    authorization_endpoint: String
}

// ============================================================================
// OIDC Code Exchange (server-side token exchange)
// ============================================================================

@http(method: "POST", uri: "/v1/oidc/exchange")
@documentation("Exchanges an OIDC authorization code for tokens server-side, fetches userinfo, and checks account status")
operation OIDCCodeExchange {
    input: OIDCCodeExchangeInput
    output: OIDCCodeExchangeOutput
    errors: [AuthenticationException, ValidationException]
}

@input
structure OIDCCodeExchangeInput {
    @required
    code: String

    @required
    code_verifier: String

    @required
    redirect_uri: String
}

@output
structure OIDCCodeExchangeOutput {
    @required
    email: String

    @required
    access_token: String

    @required
    account_exists: Boolean
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
