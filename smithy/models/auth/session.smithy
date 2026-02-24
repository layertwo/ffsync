$version: "2"

namespace layertwo.ffsync

@documentation("FxA session management resource")
resource Session {
    operations: [SessionStatus, SessionDestroy]
}

// ============================================================================
// Session Status
// ============================================================================

@readonly
@http(method: "GET", uri: "/v1/session/status")
@documentation("Check session validity")
operation SessionStatus {
    input: SessionStatusInput
    output: SessionStatusOutput
    errors: [AuthenticationException]
}

@input
structure SessionStatusInput {}

@output
structure SessionStatusOutput {
    @required
    @documentation("Session state (e.g. 'verified')")
    state: String

    @required
    @documentation("Account unique identifier")
    uid: String
}

// ============================================================================
// Session Destroy
// ============================================================================

@idempotent
@http(method: "POST", uri: "/v1/session/destroy")
@documentation("Destroy the current session")
operation SessionDestroy {
    input: SessionDestroyInput
    output: SessionDestroyOutput
    errors: [AuthenticationException]
}

@input
structure SessionDestroyInput {}

@output
structure SessionDestroyOutput {}
