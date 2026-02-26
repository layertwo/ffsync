$version: "2"

namespace layertwo.ffsync

@documentation("Root storage resource containing all user collections and metadata")
resource Storage {
    resources: [
        Collection
        StorageInfo
    ]
    delete: DeleteAllStorage
}

@documentation("Root endpoint for deleting all user data")
resource RootStorage {
    delete: DeleteAllRootStorage
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
        ConfigurationInfo
    ]
    read: GetStorageInfo
}

@documentation("Collection count information")
resource CollectionCountsResource { read: GetCollectionCounts }

@documentation("Collection usage information")
resource CollectionUsageResource { read: GetCollectionUsage }

@documentation("Storage quota information")
resource QuotaInfo { read: GetQuotaInfo }

@documentation("Server configuration information")
resource ConfigurationInfo { read: GetConfigurationInfo }

@idempotent
@http(method: "DELETE", uri: "/1.5/{uid}/storage")
@documentation("Delete all storage data for the authenticated user")
operation DeleteAllStorage {
    input: DeleteAllStorageInput
    output: DeleteAllStorageOutput
    errors: [
        AuthenticationException
    ]
}

@idempotent
@http(method: "DELETE", uri: "/1.5/{uid}")
@documentation("Delete all storage data for the authenticated user (root endpoint)")
operation DeleteAllRootStorage {
    input: DeleteAllRootStorageInput
    output: DeleteAllRootStorageOutput
    errors: [
        AuthenticationException
    ]
}

@readonly
@http(method: "GET", uri: "/1.5/{uid}/info/collections")
@documentation("Get metadata for all collections")
operation GetStorageInfo {
    input: GetStorageInfoInput
    output: GetStorageInfoOutput
    errors: [
        AuthenticationException
    ]
}

@readonly
@http(method: "GET", uri: "/1.5/{uid}/info/collection_counts")
@documentation("Get object counts for all collections")
operation GetCollectionCounts {
    input: GetCollectionCountsInput
    output: GetCollectionCountsOutput
    errors: [
        AuthenticationException
    ]
}

@readonly
@http(method: "GET", uri: "/1.5/{uid}/info/collection_usage")
@documentation("Get storage usage for all collections")
operation GetCollectionUsage {
    input: GetCollectionUsageInput
    output: GetCollectionUsageOutput
    errors: [
        AuthenticationException
    ]
}

@readonly
@http(method: "GET", uri: "/1.5/{uid}/info/quota")
@documentation("Get storage quota information")
operation GetQuotaInfo {
    input: GetQuotaInfoInput
    output: GetQuotaInfoOutput
    errors: [
        AuthenticationException
    ]
}

@readonly
@http(method: "GET", uri: "/1.5/{uid}/info/configuration")
@documentation("Get server configuration limits")
operation GetConfigurationInfo {
    input: GetConfigurationInfoInput
    output: GetConfigurationInfoOutput
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

/// Collection usage map (sizes in KB)
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
structure DeleteAllStorageInput {
    @httpLabel
    @required
    uid: String
}

@output
structure DeleteAllStorageOutput {
    @documentation("Timestamp when the deletion was completed")
    modified: Timestamp
}

@input
structure DeleteAllRootStorageInput {
    @httpLabel
    @required
    uid: String
}

@output
structure DeleteAllRootStorageOutput {
    @documentation("Timestamp when the deletion was completed")
    modified: Timestamp
}

// Info Operations
structure GetStorageInfoInput {
    @httpLabel
    @required
    uid: String
}

structure GetStorageInfoOutput {
    @documentation("Map of collection names to their last modified timestamps")
    collections: CollectionTimestamps
}

/// Collection timestamps map (collection name -> last modified timestamp)
map CollectionTimestamps {
    key: CollectionName
    value: Timestamp
}

structure GetCollectionCountsInput {
    @httpLabel
    @required
    uid: String
}

structure GetCollectionCountsOutput {
    @documentation("Map of collection names to object counts")
    counts: CollectionCounts
}

structure GetCollectionUsageInput {
    @httpLabel
    @required
    uid: String
}

structure GetCollectionUsageOutput {
    @documentation("Map of collection names to usage in KB")
    usage: CollectionUsage
}

structure GetQuotaInfoInput {
    @httpLabel
    @required
    uid: String
}

structure GetQuotaInfoOutput {
    @documentation("Two-item list: [usage_kb, quota_kb or null]")
    @required
    quota: QuotaArray
}

/// Quota array: [usage, quota or null]
list QuotaArray {
    member: Long
}

structure GetConfigurationInfoInput {
    @httpLabel
    @required
    uid: String
}

structure GetConfigurationInfoOutput {
    @documentation("Maximum number of records per POST request")
    max_post_records: Integer

    @documentation("Maximum size of POST request body in bytes")
    max_post_bytes: Long

    @documentation("Maximum size of individual record in bytes")
    max_record_payload_bytes: Long

    @documentation("Maximum total size of all records in a collection")
    max_total_records: Long

    @documentation("Maximum total size of all records in bytes")
    max_total_bytes: Long
}
