$version: "2"

namespace layertwo.ffsync

@readonly
@http(method: "GET", uri: "/v1/profile")
@documentation("Get user profile using OAuth Bearer token")
operation GetProfile {
    input: GetProfileInput
    output: GetProfileOutput
    errors: [AuthenticationException]
}

@input
structure GetProfileInput {}

@output
structure GetProfileOutput {
    @required
    @documentation("Account email address")
    email: String

    @required
    @documentation("Account unique identifier")
    uid: String

    @documentation("User locale")
    locale: String
}
