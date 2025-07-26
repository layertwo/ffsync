$version: "2"

namespace layertwo.syncstorage

@documentation("Root storage resource containing all user collections and metadata")
resource Storage {
    resources: [
        Collection
        StorageInfo
    ]
    delete: DeleteAllStorage
}

// ============================================================================
// Storage Info Resource
// ============================================================================
@documentation("Storage metadata and quota information")
resource StorageInfo {
    resources: [
        CollectionCountsResource
        CollectionUsageResource
        QuotaInfo
    ]
    read: GetStorageInfo
}

@documentation("Collection count information")
resource CollectionCountsResource { read: GetCollectionCounts }

@documentation("Collection usage information")
resource CollectionUsageResource { read: GetCollectionUsage }

@documentation("Storage quota information")
resource QuotaInfo { read: GetQuotaInfo }

@idempotent
@http(method: "DELETE", uri: "/storage")
@documentation("Delete all storage data for the authenticated user")
operation DeleteAllStorage {
    input: DeleteAllStorageInput
    output: DeleteAllStorageOutput
    errors: [
        AuthenticationException
    ]
}

@readonly
@http(method: "GET", uri: "/info/collections")
@documentation("Get metadata for all collections")
operation GetStorageInfo {
    input: GetStorageInfoInput
    output: GetStorageInfoOutput
    errors: [
        AuthenticationException
    ]
}

@readonly
@http(method: "GET", uri: "/info/collection_counts")
@documentation("Get object counts for all collections")
operation GetCollectionCounts {
    input: GetCollectionCountsInput
    output: GetCollectionCountsOutput
    errors: [
        AuthenticationException
    ]
}

@readonly
@http(method: "GET", uri: "/info/collection_usage")
@documentation("Get storage usage for all collections")
operation GetCollectionUsage {
    input: GetCollectionUsageInput
    output: GetCollectionUsageOutput
    errors: [
        AuthenticationException
    ]
}

@readonly
@http(method: "GET", uri: "/info/quota")
@documentation("Get storage quota information")
operation GetQuotaInfo {
    input: GetQuotaInfoInput
    output: GetQuotaInfoOutput
    errors: [
        AuthenticationException
    ]
}

/// Collection resource data
structure CollectionData {
    @documentation("Collection name")
    @required
    name: CollectionName

    @documentation("Last modified timestamp for the collection")
    @required
    modified: Timestamp

    @documentation("Number of items in the collection")
    @required
    count: Integer

    @documentation("Total size of the collection in bytes")
    @required
    usage: Long
}

/// Collection counts map
map CollectionCounts {
    key: CollectionName
    value: Integer
}

/// Collection usage map (sizes in bytes)
map CollectionUsage {
    key: CollectionName
    value: Long
}

/// Collection data map
map CollectionDataMap {
    key: CollectionName
    value: CollectionData
}

list ObjectIdList {
    member: ObjectId
}

list StringList {
    member: String
}

@input
structure DeleteAllStorageInput {}

@output
structure DeleteAllStorageOutput {
    @documentation("Timestamp when the deletion was completed")
    modified: Timestamp
}

// Info Operations
structure GetStorageInfoInput {}

structure GetStorageInfoOutput {
    @documentation("Map of collection names to their data")
    collections: CollectionDataMap
}

structure GetCollectionCountsInput {}

structure GetCollectionCountsOutput {
    @documentation("Map of collection names to object counts")
    counts: CollectionCounts
}

structure GetCollectionUsageInput {}

structure GetCollectionUsageOutput {
    @documentation("Map of collection names to usage in bytes")
    usage: CollectionUsage
}

structure GetQuotaInfoInput {}

structure GetQuotaInfoOutput {
    @documentation("Total storage quota in bytes")
    quota: Long

    @documentation("Used storage in bytes")
    usage: Long

    @documentation("Remaining storage in bytes")
    remaining: Long
}
