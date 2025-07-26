$version: "2"

namespace layertwo.syncstorage

use smithy.framework#ValidationException

@documentation("Individual storage object within a collection")
resource BasicStorageObjectResource {
    identifiers: {
        collectionName: CollectionName
        objectId: ObjectId
    }
    read: GetBasicStorageObject
    update: UpdateBasicStorageObject
    delete: DeleteBasicStorageObject
}

structure BasicStorageObject {
    @documentation("Unique identifier within the collection")
    @required
    id: ObjectId

    @documentation("JSON payload of the storage object")
    @required
    payload: String

    @documentation("Last modified timestamp (milliseconds since epoch)")
    @required
    modified: Timestamp

    @documentation("Sort index for ordering")
    sortindex: Integer

    @documentation("Time-to-live in seconds")
    ttl: Integer
}

/// Storage Object input for create/update operations
structure BasicStorageObjectInput {
    @documentation("Unique identifier within the collection")
    @required
    id: ObjectId

    @documentation("JSON payload of the storage object")
    @required
    payload: String

    @documentation("Sort index for ordering")
    sortindex: Integer

    @documentation("Time-to-live in seconds")
    ttl: Integer
}

@readonly
@http(method: "GET", uri: "/storage/{collectionName}/{objectId}")
@documentation("Get a specific storage object")
operation GetBasicStorageObject {
    input: GetBasicStorageObjectInput
    output: GetBasicStorageObjectOutput
    errors: [
        ValidationException
        CollectionNotFoundException
        AuthenticationException
    ]
}

@idempotent
@http(method: "PUT", uri: "/storage/{collectionName}/{objectId}")
@documentation("Update a storage object")
operation UpdateBasicStorageObject {
    input: UpdateBasicStorageObjectInput
    output: UpdateBasicStorageObjectOutput
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
@http(method: "DELETE", uri: "/storage/{collectionName}/{objectId}")
@documentation("Delete a specific storage object")
operation DeleteBasicStorageObject {
    input: DeleteBasicStorageObjectInput
    output: DeleteBasicStorageObjectOutput
    errors: [
        ValidationException
        CollectionNotFoundException
        AuthenticationException
    ]
}

structure GetBasicStorageObjectInput {
    @httpLabel
    @required
    collectionName: CollectionName

    @httpLabel
    @required
    objectId: ObjectId
}

structure GetBasicStorageObjectOutput {
    @documentation("The requested storage object")
    object: BasicStorageObject

    @httpHeader("X-Last-Modified")
    lastModified: Timestamp
}

structure UpdateBasicStorageObjectInput {
    @httpLabel
    @required
    collectionName: CollectionName

    @httpLabel
    @required
    objectId: ObjectId

    @httpPayload
    @required
    object: BasicStorageObjectInput

    @httpHeader("X-If-Unmodified-Since")
    ifUnmodifiedSince: Timestamp
}

structure UpdateBasicStorageObjectOutput {
    @documentation("Updated storage object")
    object: BasicStorageObject

    @documentation("Timestamp when the object was modified")
    modified: Timestamp
}

structure DeleteBasicStorageObjectInput {
    @httpLabel
    @required
    collectionName: CollectionName

    @httpLabel
    @required
    objectId: ObjectId
}

structure DeleteBasicStorageObjectOutput {
    @documentation("Timestamp when the object was deleted")
    modified: Timestamp
}

/// Lists
list BasicStorageObjectList {
    member: BasicStorageObject
}
