$version: "2"

namespace layertwo.syncstorage

/// Collection name identifier
@pattern("^[a-zA-Z0-9._-]+$")
@length(min: 1, max: 32)
string CollectionName

/// Storage object identifier
@pattern("^[a-zA-Z0-9._-]+$")
@length(min: 1, max: 64)
string ObjectId
