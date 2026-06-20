"""Storage manager for DynamoDB operations"""

from decimal import Decimal
from typing import Dict, List, Optional

from botocore.exceptions import ClientError

from src.shared.exceptions import (
    CollectionNotFoundException,
    ServerLimitExceededException,
    StorageObjectNotFoundException,
    ValidationException,
)
from src.shared.models import (
    BasicStorageObject,
    BatchResult,
    CollectionData,
    bso_to_item,
    collection_to_item,
    get_current_timestamp,
)

_PK = "PK"
_SK = "SK"

# Batch operation limits (Requirements 3.4, 3.5, 3.7, 3.8, 4.2)
MAX_POST_RECORDS = 100  # Max BSOs per batch
MAX_POST_BYTES = 2 * 1024 * 1024  # 2 MB total payload
MAX_IDS_PER_REQUEST = 100  # Max IDs in ids= parameter


class StorageManager:
    """Manages storage operations with DynamoDB"""

    def __init__(self, table):
        """Initialize StorageManager

        Args:
            table: DynamoDB Table resource
        """
        self.table = table

    def _collection_pk(self, user_id: str, collection_name: str) -> str:
        """Generate partition key for collection scoped to user"""
        return f"USER#{user_id}#COLLECTION#{collection_name}"

    def _metadata_sk(self) -> str:
        """Generate sort key for collection metadata"""
        return "METADATA"

    def _object_sk(self, object_id: str) -> str:
        """Generate sort key for storage object"""
        return f"OBJECT#{object_id}"

    def _batch_get_existing_objects(
        self, pk: str, object_ids: list[str]
    ) -> dict[str, BasicStorageObject]:
        """Batch fetch existing BSOs using BatchGetItem.

        Returns a dict mapping object_id -> BasicStorageObject for objects that exist.
        Objects not found are simply omitted from the result.

        Uses the resource's low-level client (self.table.meta.client) which
        auto-serializes request params and auto-deserializes response params,
        so we pass/receive plain Python values (not DynamoDB wire format).
        """
        if not object_ids:
            return {}

        result = {}
        # Process in chunks of 100 (BatchGetItem limit)
        for i in range(0, len(object_ids), 100):
            chunk = object_ids[i : i + 100]
            keys = [
                {
                    _PK: pk,
                    _SK: self._object_sk(oid),
                }
                for oid in chunk
            ]

            response = self.table.meta.client.batch_get_item(
                RequestItems={self.table.name: {"Keys": keys}}
            )

            for item in response.get("Responses", {}).get(self.table.name, []):
                obj = BasicStorageObject.model_validate(item)
                result[obj.id] = obj

            # Handle unprocessed keys with retry
            unprocessed = response.get("UnprocessedKeys", {}).get(self.table.name)
            while unprocessed:  # pragma: nocover
                response = self.table.meta.client.batch_get_item(
                    RequestItems={self.table.name: unprocessed}
                )
                for item in response.get("Responses", {}).get(self.table.name, []):
                    obj = BasicStorageObject.model_validate(item)
                    result[obj.id] = obj
                unprocessed = response.get("UnprocessedKeys", {}).get(self.table.name)

        return result

    def get_collection(self, user_id: str, collection_name: str) -> CollectionData:
        """Get collection metadata

        Args:
            user_id: User ID for scoping
            collection_name: Name of the collection

        Returns:
            CollectionData object

        Raises:
            CollectionNotFoundException: If collection doesn't exist
        """
        try:
            response = self.table.get_item(
                Key={
                    "PK": self._collection_pk(user_id, collection_name),
                    "SK": self._metadata_sk(),
                },
            )

            if "Item" not in response:
                raise CollectionNotFoundException(f"Collection '{collection_name}' not found")

            item = response["Item"]
            return CollectionData.model_validate(item)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                raise CollectionNotFoundException(f"Collection '{collection_name}' not found")
            raise

    def get_storage_object(
        self, user_id: str, collection_name: str, object_id: str
    ) -> BasicStorageObject:
        """Get a storage object

        Args:
            user_id: User ID for scoping
            collection_name: Name of the collection
            object_id: ID of the object

        Returns:
            BasicStorageObject

        Raises:
            StorageObjectNotFoundException: If object doesn't exist
        """
        try:
            response = self.table.get_item(
                Key={
                    "PK": self._collection_pk(user_id, collection_name),
                    "SK": self._object_sk(object_id),
                },
            )

            if "Item" not in response:
                raise StorageObjectNotFoundException(
                    f"Object '{object_id}' not found in collection '{collection_name}'"
                )

            item = response["Item"]
            return BasicStorageObject.model_validate(item)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                raise StorageObjectNotFoundException(f"Object '{object_id}' not found")
            raise

    def _write_batch_objects(
        self,
        user_id: str,
        collection_name: str,
        objects: List[BasicStorageObject],
        collection_exists: bool,
        modified: float,
        ttls: Optional[dict[str, int]] = None,
    ) -> tuple[list[str], dict, int, int]:
        """Write a batch of BSOs using BatchGetItem + batch_writer.

        Returns (success, failed, new_objects_count, usage_delta).
        """
        pk = self._collection_pk(user_id, collection_name)

        # Batch-fetch all existing objects in one call
        existing_map = {}
        if collection_exists:
            existing_map = self._batch_get_existing_objects(pk, [obj.id for obj in objects])

        success = []
        failed = {}
        new_objects_count = 0
        usage_delta = 0

        # Build all items and compute deltas before writing
        items_to_write = []
        for obj in objects:
            try:
                existing_obj = existing_map.get(obj.id)
                if existing_obj is not None:
                    obj_delta = len(obj.payload) - len(existing_obj.payload)
                    is_new_bso = False
                else:
                    obj_delta = len(obj.payload)
                    is_new_bso = True

                updated_obj = BasicStorageObject(
                    id=obj.id,
                    payload=obj.payload,
                    modified=modified,
                    sortindex=obj.sortindex,
                )
                obj_ttl = (ttls or {}).get(obj.id)
                obj_item = bso_to_item(updated_obj, user_id, collection_name, ttl=obj_ttl)
                items_to_write.append((obj.id, obj_item, obj_delta, is_new_bso))
            except Exception as e:  # pragma: nocover
                failed[obj.id] = [str(e)]

        # Write all items using batch_writer (auto-batches 25 per BatchWriteItem).
        # Note: batch_writer buffers items; errors surface on __exit__, not per-item.
        # If the flush fails, the entire batch fails as an exception from the context manager.
        with self.table.batch_writer() as batch:
            for obj_id, obj_item, obj_delta, is_new_bso in items_to_write:
                try:
                    batch.put_item(Item=obj_item)
                    success.append(obj_id)
                    usage_delta += obj_delta
                    if is_new_bso:
                        new_objects_count += 1
                except Exception as e:  # pragma: nocover
                    failed[obj_id] = [str(e)]

        return success, failed, new_objects_count, usage_delta

    def create_or_update_collection(
        self,
        user_id: str,
        collection_name: str,
        objects: Optional[List[BasicStorageObject]] = None,
        if_unmodified_since: Optional[float] = None,
        ttls: Optional[dict[str, int]] = None,
    ) -> tuple[CollectionData, BatchResult]:
        """Create or update a collection

        Args:
            user_id: User ID for scoping
            collection_name: Name of the collection
            objects: Optional list of objects to add
            if_unmodified_since: Optional timestamp for optimistic concurrency control

        Returns:
            Tuple of (CollectionData, BatchResult)

        Raises:
            ServerLimitExceededException: If batch limits exceeded
            PreconditionFailedException: If collection modified since if_unmodified_since
        """
        from src.shared.exceptions import PreconditionFailedException

        objects = objects or []

        # Validate batch limits (Requirements 3.4, 3.5)
        if len(objects) > MAX_POST_RECORDS:
            raise ServerLimitExceededException(
                f"Batch contains {len(objects)} records, maximum is {MAX_POST_RECORDS}"
            )

        total_bytes = sum(len(obj.payload.encode("utf-8")) for obj in objects)
        if total_bytes > MAX_POST_BYTES:
            raise ServerLimitExceededException(
                f"Batch size {total_bytes} bytes exceeds maximum {MAX_POST_BYTES} bytes"
            )

        # Detect whether the collection already exists (needed for count/usage accounting)
        try:
            existing_collection = self.get_collection(user_id, collection_name)
            collection_exists = True
        except CollectionNotFoundException:
            collection_exists = False
            existing_collection = None

        # Check optimistic concurrency control (Requirements 5.1, 5.2, 5.3)
        if if_unmodified_since is not None and existing_collection is not None:
            existing_modified_ts = existing_collection.modified

            # if_unmodified_since=0 means "create only if not exists"
            if if_unmodified_since == 0:
                raise PreconditionFailedException(
                    f"Collection '{collection_name}' already exists (create-only mode)"
                )

            # Check if collection was modified after if_unmodified_since
            if existing_modified_ts > if_unmodified_since:
                raise PreconditionFailedException(
                    f"Collection '{collection_name}' was modified since {if_unmodified_since}"
                )

        modified = get_current_timestamp()

        # Write objects using batch operations
        success, failed, new_objects_count, usage_delta = self._write_batch_objects(
            user_id, collection_name, objects, collection_exists, modified, ttls=ttls
        )

        # Write collection metadata after objects so counts reflect actual success
        if existing_collection is not None:
            # Atomically update existing metadata with ADD to avoid race conditions
            new_count = existing_collection.count + new_objects_count
            new_usage = existing_collection.usage + usage_delta
            self.table.update_item(
                Key={
                    "PK": self._collection_pk(user_id, collection_name),
                    "SK": self._metadata_sk(),
                },
                UpdateExpression="SET #modified = :modified, #name = :name, #user_id = :user_id"
                " ADD #count :count_delta, #usage :usage_delta",
                ExpressionAttributeNames={
                    "#modified": "modified",
                    "#name": "name",
                    "#user_id": "user_id",
                    "#count": "count",
                    "#usage": "usage",
                },
                ExpressionAttributeValues={
                    ":modified": Decimal(str(modified)),
                    ":name": collection_name,
                    ":user_id": user_id,
                    ":count_delta": new_objects_count,
                    ":usage_delta": usage_delta,
                },
            )
        else:
            # New collection — write full metadata with put_item
            new_count = new_objects_count
            new_usage = usage_delta
            collection_data = CollectionData(
                name=collection_name, modified=modified, count=new_count, usage=new_usage
            )
            self.table.put_item(Item=collection_to_item(collection_data, user_id))

        collection_data = CollectionData(
            name=collection_name, modified=modified, count=new_count, usage=new_usage
        )
        batch_result = BatchResult(success=success, failed=failed, modified=modified)

        return collection_data, batch_result

    def update_collection(
        self,
        user_id: str,
        collection_name: str,
        objects: List[BasicStorageObject],
        if_unmodified_since: Optional[float] = None,
        ttls: Optional[dict[str, int]] = None,
    ) -> tuple[CollectionData, BatchResult]:
        """Update a collection

        Args:
            user_id: User ID for scoping
            collection_name: Name of the collection
            objects: List of objects to update
            if_unmodified_since: Optional timestamp for optimistic concurrency control

        Returns:
            Tuple of (CollectionData, BatchResult)

        Raises:
            ServerLimitExceededException: If batch limits exceeded
            PreconditionFailedException: If collection modified since if_unmodified_since
        """
        from src.shared.exceptions import PreconditionFailedException

        # Validate batch limits
        if len(objects) > MAX_POST_RECORDS:
            raise ServerLimitExceededException(
                f"Batch contains {len(objects)} records, maximum is {MAX_POST_RECORDS}"
            )

        total_bytes = sum(len(obj.payload.encode("utf-8")) for obj in objects)
        if total_bytes > MAX_POST_BYTES:
            raise ServerLimitExceededException(
                f"Batch size {total_bytes} bytes exceeds maximum {MAX_POST_BYTES} bytes"
            )

        # Get current collection metadata
        try:
            collection = self.get_collection(user_id, collection_name)
        except CollectionNotFoundException:
            raise

        # Check optimistic concurrency control
        if if_unmodified_since is not None:
            existing_modified_ts = collection.modified
            if existing_modified_ts > if_unmodified_since:
                raise PreconditionFailedException(
                    f"Collection '{collection_name}' was modified since {if_unmodified_since}"
                )

        modified = get_current_timestamp()

        # Write objects using batch operations
        success, failed, new_objects_count, usage_delta = self._write_batch_objects(
            user_id, collection_name, objects, True, modified, ttls=ttls
        )

        # Atomically update collection metadata with ADD to avoid race conditions
        new_usage = collection.usage + usage_delta
        new_count = collection.count + new_objects_count

        self.table.update_item(
            Key={
                "PK": self._collection_pk(user_id, collection_name),
                "SK": self._metadata_sk(),
            },
            UpdateExpression="SET #modified = :modified, #name = :name, #user_id = :user_id"
            " ADD #count :count_delta, #usage :usage_delta",
            ExpressionAttributeNames={
                "#modified": "modified",
                "#name": "name",
                "#user_id": "user_id",
                "#count": "count",
                "#usage": "usage",
            },
            ExpressionAttributeValues={
                ":modified": Decimal(str(modified)),
                ":name": collection_name,
                ":user_id": user_id,
                ":count_delta": new_objects_count,
                ":usage_delta": usage_delta,
            },
        )

        collection_data = CollectionData(
            name=collection_name, modified=modified, count=new_count, usage=new_usage
        )
        batch_result = BatchResult(success=success, failed=failed, modified=modified)

        return collection_data, batch_result

    def delete_collection(self, user_id: str, collection_name: str) -> float:
        """Delete a collection

        Args:
            user_id: User ID for scoping
            collection_name: Name of the collection

        Returns:
            Modified timestamp

        Raises:
            CollectionNotFoundException: If collection doesn't exist
        """
        # Verify collection exists
        self.get_collection(user_id, collection_name)

        modified = get_current_timestamp()
        pk = self._collection_pk(user_id, collection_name)

        # Query all items (only keys needed) and batch-delete
        response = self.table.query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": pk},
            ProjectionExpression="PK, SK",
        )

        with self.table.batch_writer() as batch:
            for item in response.get("Items", []):
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})

            while "LastEvaluatedKey" in response:
                response = self.table.query(
                    KeyConditionExpression="PK = :pk",
                    ExpressionAttributeValues={":pk": pk},
                    ProjectionExpression="PK, SK",
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                for item in response.get("Items", []):
                    batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})

        return modified

    def list_collections(self, user_id: str) -> List[CollectionData]:
        """List all collections for a user

        Args:
            user_id: User ID for scoping

        Returns:
            List of CollectionData objects
        """
        collections = []

        # Query GSI for all collections for this user
        response = self.table.query(
            IndexName="UserCollectionsIndex",
            KeyConditionExpression="user_id = :user_id",
            ExpressionAttributeValues={":user_id": user_id},
        )

        for item in response.get("Items", []):
            collection = CollectionData.model_validate(item)
            collections.append(collection)

        # Handle pagination if there are more results
        while "LastEvaluatedKey" in response:
            response = self.table.query(
                IndexName="UserCollectionsIndex",
                KeyConditionExpression="user_id = :user_id",
                ExpressionAttributeValues={":user_id": user_id},
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            for item in response.get("Items", []):
                collection = CollectionData.model_validate(item)
                collections.append(collection)

        return collections

    def _get_objects_by_ids(self, pk: str, id_set: frozenset[str]) -> list[BasicStorageObject]:
        """Fetch specific BSOs by ID using BatchGetItem."""
        existing = self._batch_get_existing_objects(pk, list(id_set))
        return list(existing.values())

    def get_collection_objects(
        self,
        user_id: str,
        collection_name: str,
        ids: Optional[str] = None,
        newer: Optional[float] = None,
        older: Optional[float] = None,
        sort: str = "newest",
        limit: int = 100,
        offset: int = 0,
        full: bool = True,
    ) -> Dict:
        """Get objects from a collection with filtering

        Args:
            user_id: User ID for scoping
            collection_name: Name of the collection
            ids: Comma-separated list of object IDs
            newer: Only return objects modified after this timestamp
            older: Only return objects modified before this timestamp
            sort: Sort order (newest, oldest, index)
            limit: Maximum number of objects to return
            offset: Offset for pagination
            full: Whether to return full objects or just IDs

        Returns:
            Dict with items, more, next_offset, last_modified
            Returns empty list for non-existent collections (Requirement 2.2)

        Raises:
            ValidationException: If more than 100 IDs provided
        """
        # Parse and validate IDs parameter once (Requirement 2.5)
        # Note: frozenset deduplicates — validates unique ID count, not raw count
        id_set = None
        if ids:
            id_set = frozenset(id.strip() for id in ids.split(","))
            if len(id_set) > MAX_IDS_PER_REQUEST:
                raise ValidationException(
                    f"Cannot request more than {MAX_IDS_PER_REQUEST} IDs, got {len(id_set)}"
                )

        pk = self._collection_pk(user_id, collection_name)

        if id_set is not None:
            # Use BatchGetItem for targeted ID lookups
            items = self._get_objects_by_ids(pk, id_set)
        else:
            # Query all objects in collection with server-side filtering
            expr_values: dict = {
                ":pk": pk,
                ":obj_prefix": "OBJECT#",
            }

            # Push newer/older filters to DynamoDB FilterExpression
            filter_parts = []
            if newer is not None:
                filter_parts.append("modified > :newer")
                expr_values[":newer"] = Decimal(str(newer))
            if older is not None:
                filter_parts.append("modified < :older")
                expr_values[":older"] = Decimal(str(older))

            query_kwargs: dict = {
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :obj_prefix)",
                "ExpressionAttributeValues": expr_values,
            }
            if filter_parts:
                query_kwargs["FilterExpression"] = " AND ".join(filter_parts)

            # Use ProjectionExpression when full objects aren't needed
            if not full:
                query_kwargs["ProjectionExpression"] = "SK, modified, sortindex"

            response = self.table.query(**query_kwargs)
            items = [BasicStorageObject.model_validate(item) for item in response.get("Items", [])]

            # Handle pagination from DynamoDB
            while "LastEvaluatedKey" in response:
                query_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
                response = self.table.query(**query_kwargs)
                items.extend(
                    BasicStorageObject.model_validate(item) for item in response.get("Items", [])
                )

        # Apply newer/older filters for BatchGetItem path (not pushed to DynamoDB)
        if id_set is not None:
            if newer is not None:
                items = [obj for obj in items if obj.modified > newer]
            if older is not None:
                items = [obj for obj in items if obj.modified < older]

        # Sort items
        if sort == "newest":
            items.sort(key=lambda x: x.modified, reverse=True)
        elif sort == "oldest":
            items.sort(key=lambda x: x.modified)
        elif sort == "index":
            items.sort(key=lambda x: (x.sortindex or 0, x.modified), reverse=True)

        # Get last modified (epoch seconds, float)
        if items:
            last_modified = max(obj.modified for obj in items)
        else:
            last_modified = 0.0

        # Apply pagination
        total_items = len(items)
        items = items[offset : offset + limit]

        # Check if there are more items
        more = offset + limit < total_items
        next_offset = offset + limit if more else None

        return {
            "items": items,
            "more": more,
            "next_offset": next_offset,
            "last_modified": last_modified,
        }

    def update_storage_object(
        self,
        user_id: str,
        collection_name: str,
        object_id: str,
        if_unmodified_since: Optional[float] = None,
        **kwargs,
    ) -> BasicStorageObject:
        """Update a storage object

        Args:
            user_id: User ID for scoping
            collection_name: Name of the collection
            object_id: ID of the object
            if_unmodified_since: Optional timestamp for optimistic concurrency control
            **kwargs: Fields to update

        Returns:
            Updated BasicStorageObject

        Raises:
            StorageObjectNotFoundException: If object doesn't exist
            PreconditionFailedException: If object modified since if_unmodified_since
        """
        from src.shared.exceptions import PreconditionFailedException

        # Get existing object to verify it exists
        is_new_bso = False
        try:
            existing_obj = self.get_storage_object(user_id, collection_name, object_id)

            # Check optimistic concurrency control (Requirements 5.1, 5.2, 5.3)
            if if_unmodified_since is not None:
                existing_modified_ts = existing_obj.modified

                # if_unmodified_since=0 means "create only if not exists"
                if if_unmodified_since == 0:
                    raise PreconditionFailedException(
                        f"Object '{object_id}' already exists (create-only mode)"
                    )

                # Check if object was modified after if_unmodified_since
                if existing_modified_ts > if_unmodified_since:
                    raise PreconditionFailedException(
                        f"Object '{object_id}' was modified since {if_unmodified_since}"
                    )
        except StorageObjectNotFoundException:
            # Object doesn't exist
            is_new_bso = True
            if if_unmodified_since is not None and if_unmodified_since != 0:
                # Can't check precondition on non-existent object
                raise PreconditionFailedException(
                    f"Object '{object_id}' does not exist, cannot check precondition"
                )
            # For new objects, create with default values
            existing_obj = BasicStorageObject(
                id=object_id,
                payload="",
                modified=0.0,
                sortindex=None,
            )

        modified = get_current_timestamp()

        # Update provided fields. `ttl` is DynamoDB-only and isn't a wire field;
        # callers pass it via kwargs and we thread it through to bso_to_item.
        payload = kwargs.get("payload", existing_obj.payload)
        sortindex = kwargs.get("sortindex", existing_obj.sortindex)
        ttl = kwargs.get("ttl")

        obj = BasicStorageObject(
            id=object_id,
            payload=payload,
            modified=modified,
            sortindex=sortindex,
        )
        self.table.put_item(Item=bso_to_item(obj, user_id, collection_name, ttl=ttl))

        # Upsert collection metadata so list_collections reflects this write.
        # DynamoDB update_item creates the item if it doesn't exist, and ADD
        # initialises missing numeric attributes to 0 before adding.
        usage_delta = len(payload) - len(existing_obj.payload)
        count_delta = 1 if is_new_bso else 0

        self.table.update_item(
            Key={
                "PK": self._collection_pk(user_id, collection_name),
                "SK": self._metadata_sk(),
            },
            UpdateExpression="SET #modified = :modified, #name = :name, #user_id = :user_id"
            " ADD #count :count_delta, #usage :usage_delta",
            ExpressionAttributeNames={
                "#modified": "modified",
                "#name": "name",
                "#user_id": "user_id",
                "#count": "count",
                "#usage": "usage",
            },
            ExpressionAttributeValues={
                ":modified": Decimal(str(modified)),
                ":name": collection_name,
                ":user_id": user_id,
                ":count_delta": count_delta,
                ":usage_delta": usage_delta,
            },
        )

        return obj

    def delete_storage_object(self, user_id: str, collection_name: str, object_id: str) -> float:
        """Delete a storage object

        Args:
            user_id: User ID for scoping
            collection_name: Name of the collection
            object_id: ID of the object

        Returns:
            Modified timestamp

        Raises:
            StorageObjectNotFoundException: If object doesn't exist
        """
        # Verify object exists
        self.get_storage_object(user_id, collection_name, object_id)

        modified = get_current_timestamp()

        self.table.delete_item(
            Key={
                "PK": self._collection_pk(user_id, collection_name),
                "SK": self._object_sk(object_id),
            },
        )

        return modified

    def delete_collection_objects(
        self, user_id: str, collection_name: str, ids: List[str]
    ) -> float:
        """Delete specific BSOs from a collection (selective deletion)

        Args:
            user_id: User ID for scoping
            collection_name: Name of the collection
            ids: List of BSO IDs to delete (max 100)

        Returns:
            Modified timestamp

        Raises:
            CollectionNotFoundException: If collection doesn't exist
            ValidationException: If more than 100 IDs provided
        """
        # Validate max 100 IDs (Requirement 4.2)
        if len(ids) > MAX_IDS_PER_REQUEST:
            raise ValidationException(
                f"Cannot delete more than {MAX_IDS_PER_REQUEST} objects at once, got {len(ids)}"
            )

        # Verify collection exists (reuse for metadata update below)
        collection = self.get_collection(user_id, collection_name)

        modified = get_current_timestamp()
        pk = self._collection_pk(user_id, collection_name)

        # Batch-delete specified objects
        with self.table.batch_writer() as batch:
            for object_id in ids:
                try:
                    batch.delete_item(
                        Key={
                            "PK": pk,
                            "SK": self._object_sk(object_id),
                        },
                    )
                except Exception:  # pragma: nocover
                    # Continue deleting other objects even if one fails
                    pass

        # Update collection's last-modified time (reusing initial get_collection result)
        collection_data = CollectionData(
            name=collection_name,
            modified=modified,
            count=collection.count,
            usage=collection.usage,
        )
        self.table.put_item(Item=collection_to_item(collection_data, user_id))

        return modified

    def delete_all_storage(self, user_id: str) -> float:
        """Delete all collections and BSOs for a user

        Uses list_collections (GSI query) then delete_collection per collection,
        avoiding an expensive full-table scan.

        Args:
            user_id: User ID for scoping

        Returns:
            Deletion timestamp
        """
        modified = get_current_timestamp()

        collections = self.list_collections(user_id)
        for collection in collections:
            try:
                self.delete_collection(user_id, collection.name)
            except CollectionNotFoundException:
                # Collection was deleted concurrently; skip it
                pass

        return modified

    def get_quota(self, user_id: str) -> tuple[float, Optional[float]]:
        """Get quota information for a user

        Args:
            user_id: User ID for scoping

        Returns:
            Tuple of (usage_kb, quota_kb or None)
            - usage_kb: Current storage usage in KB
            - quota_kb: Storage quota in KB, or None if unlimited
        """
        # Calculate total usage across all collections
        collections = self.list_collections(user_id)
        total_usage_bytes = sum(col.usage for col in collections)
        usage_kb = total_usage_bytes / 1024.0

        # For now, quota is unlimited (None)
        # This can be configured per-user in the future
        quota_kb = None

        return (usage_kb, quota_kb)
