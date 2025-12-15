$version: "2"

namespace layertwo.ffsync

/// Collection name identifier
@pattern("^[a-zA-Z0-9._-]+$")
@length(min: 1, max: 32)
string CollectionName

/// Storage object identifier
@pattern("^[a-zA-Z0-9._-]+$")
@length(min: 1, max: 64)
string ObjectId

/// Client state for key rotation tracking (urlsafe-base64 + period)
@pattern("^[a-zA-Z0-9_.-]*$")
@length(min: 0, max: 32)
string ClientState
