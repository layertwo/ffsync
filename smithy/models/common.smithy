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

/// Client state for key rotation tracking (hexadecimal string)
@pattern("^[a-fA-F0-9]*$")
@length(min: 0, max: 32)
string ClientState
