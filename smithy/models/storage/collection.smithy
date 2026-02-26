$version: "2"

namespace layertwo.ffsync

use smithy.framework#ValidationException

@documentation("A collection of storage objects grouped by type (e.g., bookmarks, history)")
resource Collection {
    identifiers: {
        collectionName: CollectionName
    }
    resources: [
        BasicStorageObjectResource
    ]
    put: CreateCollection
    read: GetCollection
    update: UpdateCollection
    delete: DeleteCollection
    list: ListCollections
}

@readonly
@http(method: "GET", uri: "/1.5/{uid}/storage")
@documentation("List all collections with their metadata")
operation ListCollections {
    input: ListCollectionsInput
    output: ListCollectionsOutput
    errors: [
        AuthenticationException
    ]
}

// Collection CRUD Operations
structure ListCollectionsInput {
    @httpLabel
    @required
    uid: String
}

structure ListCollectionsOutput {
    @documentation("List of collections with their metadata")
    collections: CollectionDataList
}

list CollectionDataList {
    member: CollectionData
}

/// Wrapper structure for batch object operations
structure BatchObjectsPayload {
    @documentation("List of objects to create or update")
    @required
    objects: BasicStorageObjectInputList
}

@input
structure CreateCollectionInput {
    @httpLabel
    @required
    uid: String

    @httpLabel
    @required
    collectionName: CollectionName

    @httpPayload
    payload: BatchObjectsPayload

    @httpHeader("X-If-Unmodified-Since")
    ifUnmodifiedSince: Timestamp
}

@output
structure CreateCollectionOutput {
    @documentation("Timestamp when the collection was modified")
    @required
    modified: Timestamp

    @documentation("Successfully processed object IDs")
    success: ObjectIdList

    @documentation("Failed operations with error messages")
    failed: FailedOperations
}

@idempotent
@http(method: "POST", uri: "/1.5/{uid}/storage/{collectionName}")
@documentation("Create a new collection or batch create/update objects")
operation CreateCollection {
    input: CreateCollectionInput
    output: CreateCollectionOutput
    errors: [
        ValidationException
        ConflictException
        RequestTooLargeException
        QuotaExceededException
        AuthenticationException
    ]
}

@input
structure GetCollectionInput {
    @httpLabel
    @required
    uid: String

    @httpLabel
    @required
    collectionName: CollectionName

    @httpQuery("ids")
    @documentation("Comma-separated list of object IDs to retrieve")
    ids: String

    @httpQuery("newer")
    @documentation("Return objects newer than this timestamp")
    newer: Timestamp

    @httpQuery("older")
    @documentation("Return objects older than this timestamp")
    older: Timestamp

    @httpQuery("sort")
    @documentation("Sort order: newest, oldest, or index")
    sort: String

    @httpQuery("limit")
    @documentation("Maximum number of objects to return")
    limit: Integer

    @httpQuery("offset")
    @documentation("Number of objects to skip")
    offset: Integer

    @httpQuery("full")
    @documentation("Return full objects (1) or just IDs (0)")
    full: Boolean
}

@output
structure GetCollectionOutput {
    @documentation("Collection data (when retrieving metadata only)")
    collection: CollectionData

    @documentation("List of storage objects (when retrieving objects)")
    objects: BasicStorageObjectList

    @httpHeader("X-Last-Modified")
    lastModified: Timestamp

    @documentation("More items available (for pagination)")
    more: Boolean

    @documentation("Next offset for pagination")
    next_offset: Integer
}

@readonly
@http(method: "GET", uri: "/1.5/{uid}/storage/{collectionName}")
@documentation("Get collection metadata or retrieve objects with filtering")
operation GetCollection {
    input: GetCollectionInput
    output: GetCollectionOutput
    errors: [
        ValidationException
        CollectionNotFoundException
        AuthenticationException
    ]
}

@input
structure UpdateCollectionInput {
    @httpLabel
    @required
    uid: String

    @httpLabel
    @required
    collectionName: CollectionName

    @httpPayload
    @required
    payload: BatchObjectsPayload

    @httpHeader("X-If-Unmodified-Since")
    ifUnmodifiedSince: Timestamp
}

@output
structure UpdateCollectionOutput {
    @documentation("Updated collection data")
    collection: CollectionData

    @documentation("Batch operation result")
    batchResult: BatchResult
}

@idempotent
@http(method: "PUT", uri: "/1.5/{uid}/storage/{collectionName}")
@documentation("Update collection with batch objects")
operation UpdateCollection {
    input: UpdateCollectionInput
    output: UpdateCollectionOutput
    errors: [
        ValidationException
        ConflictException
        PreconditionFailedException
        RequestTooLargeException
        QuotaExceededException
        AuthenticationException
    ]
}

@idempotent
@http(method: "DELETE", uri: "/1.5/{uid}/storage/{collectionName}")
@documentation("Delete an entire collection")
operation DeleteCollection {
    input: DeleteCollectionInput
    output: DeleteCollectionOutput
    errors: [
        ValidationException
        CollectionNotFoundException
        AuthenticationException
    ]
}

@input
structure DeleteCollectionInput {
    @httpLabel
    @required
    uid: String

    @httpLabel
    @required
    collectionName: CollectionName

    @httpQuery("ids")
    @documentation("Comma-separated list of object IDs to delete (max 100). If omitted, deletes entire collection.")
    ids: String
}

@output
structure DeleteCollectionOutput {
    @documentation("Timestamp when the collection was deleted")
    modified: Timestamp
}

/// Batch operation result
structure BatchResult {
    @documentation("Successfully processed object IDs")
    success: ObjectIdList

    @documentation("Failed operations with error messages (ID -> error string)")
    failed: FailedOperations

    @documentation("New last modified timestamp")
    modified: Timestamp
}

/// Failed operation details (ID -> error message string)
map FailedOperations {
    key: ObjectId
    value: String
}
