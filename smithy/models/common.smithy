$version: "2"

namespace layertwo.ffsync

/// Collection name identifier
@pattern("^[a-zA-Z0-9._-]+$")
@length(min: 1, max: 32)
string CollectionName

/// Storage object identifier
///
/// The spec requires printable ASCII only: "BSO ids *must* only contain
/// printable ASCII characters". The 12-character base64-urlsafe form is a
/// client convention ("*should* be exactly 12 ... while this isn't enforced by
/// the server"), so the server must not enforce it. Mozilla's own rule is
/// `BSO_ID_REGEX = r"[ -~]{1,64}"`.
@pattern("^[ -~]+$")
@length(min: 1, max: 64)
string ObjectId

/// Client state for key rotation tracking (urlsafe-base64 + period)
@pattern("^[a-zA-Z0-9_.-]*$")
@length(min: 0, max: 32)
string ClientState
