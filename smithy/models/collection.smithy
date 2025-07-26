$version: "2"

namespace layertwo.syncstorage

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
@http(method: "GET", uri: "/storage")
@documentation("List all collections with their metadata")
operation ListCollections {
    input: ListCollectionsInput
    output: ListCollectionsOutput
    errors: [
        AuthenticationException
    ]
}

// Collection CRUD Operations
structure ListCollectionsInput {}

structure ListCollectionsOutput {
    @documentation("List of collections with their metadata")
    collections: CollectionDataList
}

list CollectionDataList {
    member: CollectionData
}

@input
structure CreateCollectionInput {
    @httpLabel
    @required
    collectionName: CollectionName

    @required
    objects: BasicStorageObjectList
}

@output
structure CreateCollectionOutput {
    @documentation("Created collection data")
    collection: CollectionData

    @documentation("Batch result if objects were provided")
    batchResult: BatchResult
}

@idempotent
@http(method: "POST", uri: "/storage/{collectionName}")
@documentation("Create a new collection")
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
    collectionName: CollectionName
}

@output
structure GetCollectionOutput {
    @documentation("Collection data")
    collection: CollectionData

    @httpHeader("X-Last-Modified")
    lastModified: Timestamp
}

@readonly
@http(method: "GET", uri: "/storage/{collectionName}")
@documentation("Get collection metadata")
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
    collectionName: CollectionName

    @required
    objects: BasicStorageObjectList

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
@http(method: "PUT", uri: "/storage/{collectionName}")
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
@http(method: "DELETE", uri: "/storage/{collectionName}")
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
    collectionName: CollectionName
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

    @documentation("Failed operations with error details")
    failed: FailedOperations

    @documentation("New last modified timestamp")
    modified: Timestamp
}

/// Failed operation details
map FailedOperations {
    key: ObjectId
    value: StringList
}
