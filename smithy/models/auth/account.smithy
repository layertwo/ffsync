$version: "2"

namespace layertwo.ffsync

use smithy.framework#ValidationException

@documentation("FxA account management resource")
resource Account {
    operations: [AccountCreate, AccountLogin, AccountStatus, AccountKeys, AccountProfile, ScopedKeyData]
}

// ============================================================================
// Account Status
// ============================================================================

@readonly
@http(method: "GET", uri: "/v1/account/status")
@documentation("Check whether an account exists for the given email")
operation AccountStatus {
    input: AccountStatusInput
    output: AccountStatusOutput
    errors: [ValidationException]
}

@input
structure AccountStatusInput {
    @httpQuery("email")
    @documentation("Email address to check")
    email: String
}

@output
structure AccountStatusOutput {
    @required
    @documentation("Whether an account exists for this email")
    exists: Boolean
}

// ============================================================================
// Account Create
// ============================================================================

@http(method: "POST", uri: "/v1/account/create")
@documentation("Create a new FxA account linked to an OIDC identity")
operation AccountCreate {
    input: AccountCreateInput
    output: AccountCreateOutput
    errors: [AuthenticationException, ValidationException, ConflictException]
}

@input
structure AccountCreateInput {
    @required
    @documentation("Email address for the account")
    email: String

    @required
    @documentation("Stretched password (authPW) as hex string")
    authPW: String
}

@output
structure AccountCreateOutput {
    @required
    @documentation("Account unique identifier")
    uid: String

    @required
    @documentation("Session token as hex string")
    sessionToken: String

    @required
    @documentation("Key fetch token as hex string")
    keyFetchToken: String

    @required
    @documentation("Whether the account is verified")
    verified: Boolean
}

// ============================================================================
// Account Login
// ============================================================================

@http(method: "POST", uri: "/v1/account/login")
@documentation("Authenticate with email and authPW, returning session and key-fetch tokens")
operation AccountLogin {
    input: AccountLoginInput
    output: AccountLoginOutput
    errors: [AuthenticationException, ValidationException]
}

@input
structure AccountLoginInput {
    @required
    @documentation("Email address")
    email: String

    @required
    @documentation("Stretched password (authPW) as hex string")
    authPW: String

    @httpQuery("keys")
    @documentation("If true, include keyFetchToken in the response")
    keys: Boolean
}

@output
structure AccountLoginOutput {
    @required
    @documentation("Account unique identifier")
    uid: String

    @required
    @documentation("Session token as hex string")
    sessionToken: String

    @documentation("Key fetch token as hex string (only if keys=true)")
    keyFetchToken: String

    @required
    @documentation("Whether the account is verified")
    verified: Boolean
}

// ============================================================================
// Account Keys
// ============================================================================

@readonly
@http(method: "GET", uri: "/v1/account/keys")
@documentation("Retrieve encrypted key bundle (kA + wrapKB). Single-use keyFetchToken auth.")
operation AccountKeys {
    input: AccountKeysInput
    output: AccountKeysOutput
    errors: [AuthenticationException, ValidationException]
}

@input
structure AccountKeysInput {}

@output
structure AccountKeysOutput {
    @required
    @documentation("Encrypted key bundle as hex string (ciphertext + HMAC)")
    bundle: String
}

// ============================================================================
// Account Profile
// ============================================================================

@readonly
@http(method: "GET", uri: "/v1/account/profile")
@documentation("Get basic account profile information")
operation AccountProfile {
    input: AccountProfileInput
    output: AccountProfileOutput
    errors: [AuthenticationException]
}

@input
structure AccountProfileInput {}

@output
structure AccountProfileOutput {
    @required
    @documentation("Account email address")
    email: String

    @required
    @documentation("Account unique identifier")
    uid: String

    @documentation("User locale")
    locale: String
}

// ============================================================================
// Scoped Key Data
// ============================================================================

@http(method: "POST", uri: "/v1/account/scoped-key-data")
@documentation("Get key metadata for sync encryption key derivation")
operation ScopedKeyData {
    input: ScopedKeyDataInput
    output: ScopedKeyDataOutput
    errors: [AuthenticationException, ValidationException]
}

@input
structure ScopedKeyDataInput {
    @required
    @documentation("OAuth client ID")
    client_id: String

    @required
    @documentation("OAuth scope")
    scope: String
}

@output
structure ScopedKeyDataOutput {
    @required
    @documentation("Map of scope identifiers to key metadata")
    scopes: ScopedKeyDataMap
}

map ScopedKeyDataMap {
    key: String
    value: ScopedKeyDataEntry
}

structure ScopedKeyDataEntry {
    @required
    @documentation("Scope identifier")
    identifier: String

    @required
    @documentation("Key rotation secret as hex string")
    keyRotationSecret: String

    @required
    @documentation("Key rotation timestamp in epoch milliseconds")
    keyRotationTimestamp: Long
}
