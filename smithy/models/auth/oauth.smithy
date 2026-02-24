$version: "2"

namespace layertwo.ffsync

use smithy.framework#ValidationException

@documentation("OAuth token issuance resource")
resource OAuth {
    operations: [OAuthAuthorization, OAuthToken, OAuthDestroy]
}

// ============================================================================
// OAuth Authorization
// ============================================================================

@http(method: "POST", uri: "/v1/oauth/authorization")
@documentation("Issue an OAuth authorization code")
operation OAuthAuthorization {
    input: OAuthAuthorizationInput
    output: OAuthAuthorizationOutput
    errors: [AuthenticationException, ValidationException]
}

@input
structure OAuthAuthorizationInput {
    @required
    @documentation("OAuth client ID")
    client_id: String

    @required
    @documentation("Requested scopes")
    scope: String

    @required
    @documentation("CSRF state parameter")
    state: String

    @documentation("PKCE code challenge")
    code_challenge: String

    @documentation("PKCE code challenge method (S256)")
    code_challenge_method: String

    @documentation("Access type (online or offline)")
    access_type: String
}

@output
structure OAuthAuthorizationOutput {
    @required
    @documentation("Authorization code")
    code: String

    @required
    @documentation("State parameter echoed back")
    state: String

    @required
    @documentation("Redirect URI")
    redirect: String
}

// ============================================================================
// OAuth Token
// ============================================================================

@http(method: "POST", uri: "/v1/oauth/token")
@documentation("Exchange authorization code or refresh token for access token")
operation OAuthToken {
    input: OAuthTokenInput
    output: OAuthTokenOutput
    errors: [ValidationException, AuthenticationException]
}

@input
structure OAuthTokenInput {
    @required
    @documentation("Grant type: authorization_code or refresh_token")
    grant_type: String

    @documentation("OAuth client ID")
    client_id: String

    @documentation("Authorization code (for authorization_code grant)")
    code: String

    @documentation("PKCE code verifier (for authorization_code grant)")
    code_verifier: String

    @documentation("Refresh token (for refresh_token grant)")
    refresh_token: String

    @documentation("Requested scope for token refresh")
    scope: String

    @documentation("Time to live for the access token in seconds")
    ttl: Integer
}

@output
structure OAuthTokenOutput {
    @required
    @documentation("JWT access token")
    access_token: String

    @required
    @documentation("Token type (always 'bearer')")
    token_type: String

    @required
    @documentation("Token validity duration in seconds")
    expires_in: Integer

    @required
    @documentation("Granted scope")
    scope: String

    @documentation("Refresh token for obtaining new access tokens")
    refresh_token: String

    @documentation("Authentication timestamp in seconds")
    auth_at: Long

    @documentation("Keys JWE (encrypted key data)")
    keys_jwe: String
}

// ============================================================================
// OAuth Destroy
// ============================================================================

@idempotent
@http(method: "POST", uri: "/v1/oauth/destroy")
@documentation("Revoke an OAuth token")
operation OAuthDestroy {
    input: OAuthDestroyInput
    output: OAuthDestroyOutput
    errors: [ValidationException]
}

@input
structure OAuthDestroyInput {
    @required
    @documentation("Token to revoke")
    token: String

    @documentation("OAuth client ID")
    client_id: String
}

@output
structure OAuthDestroyOutput {}
