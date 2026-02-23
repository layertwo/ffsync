"""Storage manager for DynamoDB operations"""

from datetime import datetime, timezone
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

    def _encode_basic_storage_object(
        self, user_id: str, collection_name: str, obj: BasicStorageObject
    ) -> dict:
        """Encode BasicStorageObject to DynamoDB format"""
        obj_data = obj.to_dict()
        obj_data[_PK] = self._collection_pk(user_id, collection_name)
        obj_data[_SK] = self._object_sk(obj.id)

        # Add DynamoDB TTL attribute if ttl is set (Requirement 11.1-11.4)
        if obj.ttl is not None:
            # Calculate expiry as current_time + ttl (in seconds)
            current_time = int(datetime.now(tz=timezone.utc).timestamp())
            obj_data["expiry"] = current_time + obj.ttl

        return obj_data

    def _encode_collection_data(self, user_id: str, collection_data: CollectionData) -> dict:
        """Encode CollectionData to DynamoDB format"""
        col_data = collection_data.to_dict()
        col_data[_PK] = self._collection_pk(user_id, collection_data.name)
        col_data[_SK] = self._metadata_sk()
        col_data["user_id"] = user_id  # GSI partition key for efficient user queries
        return col_data

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
            return CollectionData.from_dict(item)
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
            return BasicStorageObject.from_dict(item)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                raise StorageObjectNotFoundException(f"Object '{object_id}' not found")
            raise

    def create_or_update_collection(
        self,
        user_id: str,
        collection_name: str,
        objects: Optional[List[BasicStorageObject]] = None,
        if_unmodified_since: Optional[float] = None,
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
            existing_modified_ts = existing_collection.modified.timestamp()

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

        modified_timestamp = get_current_timestamp()
        modified = datetime.fromtimestamp(modified_timestamp, tz=timezone.utc)

        # Write objects first, tracking new vs updated and actual usage delta
        success = []
        failed = {}
        new_objects_count = 0
        usage_delta = 0

        for obj in objects:
            try:
                is_new_bso = False
                if collection_exists:
                    # Check if object already exists to compute accurate usage delta
                    try:
                        existing_obj = self.get_storage_object(user_id, collection_name, obj.id)
                        obj_delta = len(obj.payload) - len(existing_obj.payload)
                    except StorageObjectNotFoundException:
                        obj_delta = len(obj.payload)
                        is_new_bso = True
                else:
                    # Collection is new — every object is new by definition
                    obj_delta = len(obj.payload)
                    is_new_bso = True

                updated_obj = BasicStorageObject(
                    id=obj.id,
                    payload=obj.payload,
                    modified=modified,
                    sortindex=obj.sortindex,
                    ttl=obj.ttl,
                )
                obj_item = self._encode_basic_storage_object(user_id, collection_name, updated_obj)
                self.table.put_item(Item=obj_item)
                success.append(obj.id)
                usage_delta += obj_delta
                if is_new_bso:
                    new_objects_count += 1  # only count new BSOs that were successfully written
            except Exception as e:
                failed[obj.id] = [str(e)]

        # Write collection metadata after objects so counts reflect actual success
        if collection_exists:
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
                    ":modified": Decimal(str(modified_timestamp)),
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
            metadata_item = self._encode_collection_data(user_id, collection_data)
            self.table.put_item(Item=metadata_item)

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
            existing_modified_ts = collection.modified.timestamp()
            if existing_modified_ts > if_unmodified_since:
                raise PreconditionFailedException(
                    f"Collection '{collection_name}' was modified since {if_unmodified_since}"
                )

        modified_timestamp = get_current_timestamp()
        modified = datetime.fromtimestamp(modified_timestamp, tz=timezone.utc)

        # Update objects
        success = []
        failed = {}
        usage_delta = 0
        new_objects_count = 0  # only count genuinely new BSOs

        for obj in objects:
            try:
                # Determine usage delta: subtract old payload size if BSO already exists
                is_new_bso = False
                try:
                    existing_obj = self.get_storage_object(user_id, collection_name, obj.id)
                    obj_delta = len(obj.payload) - len(existing_obj.payload)
                except StorageObjectNotFoundException:
                    obj_delta = len(obj.payload)
                    is_new_bso = True

                # Create object with updated timestamp
                updated_obj = BasicStorageObject(
                    id=obj.id,
                    payload=obj.payload,
                    modified=modified,
                    sortindex=obj.sortindex,
                    ttl=obj.ttl,
                )
                obj_item = self._encode_basic_storage_object(user_id, collection_name, updated_obj)

                self.table.put_item(Item=obj_item)
                success.append(obj.id)
                usage_delta += obj_delta
                if is_new_bso:
                    new_objects_count += 1  # only count new BSOs that were successfully written
            except Exception as e:
                failed[obj.id] = [str(e)]

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
                ":modified": Decimal(str(modified_timestamp)),
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

        # Query all items in the collection, paginating through all results
        response = self.table.query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": pk},
        )

        for item in response.get("Items", []):
            self.table.delete_item(
                Key={"PK": item["PK"], "SK": item["SK"]},
            )

        while "LastEvaluatedKey" in response:
            response = self.table.query(
                KeyConditionExpression="PK = :pk",
                ExpressionAttributeValues={":pk": pk},
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            for item in response.get("Items", []):
                self.table.delete_item(
                    Key={"PK": item["PK"], "SK": item["SK"]},
                )

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
            collection = CollectionData.from_dict(item)
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
                collection = CollectionData.from_dict(item)
                collections.append(collection)

        return collections

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
        # Validate IDs parameter (Requirement 2.5)
        if ids:
            id_list = [id.strip() for id in ids.split(",")]
            if len(id_list) > MAX_IDS_PER_REQUEST:
                raise ValidationException(
                    f"Cannot request more than {MAX_IDS_PER_REQUEST} IDs, got {len(id_list)}"
                )

        pk = self._collection_pk(user_id, collection_name)

        # Query all objects in collection
        # Note: If collection doesn't exist, query will return empty results
        response = self.table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :obj_prefix)",
            ExpressionAttributeValues={
                ":pk": pk,
                ":obj_prefix": "OBJECT#",
            },
        )

        items = []
        for item in response.get("Items", []):
            obj = BasicStorageObject.from_dict(item)
            items.append(obj)

        # Filter by IDs if specified
        if ids:
            id_list = [id.strip() for id in ids.split(",")]
            items = [obj for obj in items if obj.id in id_list]

        # Filter by timestamp - convert float timestamps to datetime for comparison
        if newer is not None:
            newer_dt = datetime.fromtimestamp(newer, tz=timezone.utc)
            items = [obj for obj in items if obj.modified > newer_dt]
        if older is not None:
            older_dt = datetime.fromtimestamp(older, tz=timezone.utc)
            items = [obj for obj in items if obj.modified < older_dt]

        # Sort items
        if sort == "newest":
            items.sort(key=lambda x: x.modified, reverse=True)
        elif sort == "oldest":
            items.sort(key=lambda x: x.modified)
        elif sort == "index":
            items.sort(key=lambda x: (x.sortindex or 0, x.modified), reverse=True)

        # Get last modified - return as datetime
        if items:
            last_modified = max(obj.modified for obj in items)
        else:
            last_modified = datetime.fromtimestamp(0.0, tz=timezone.utc)

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
        try:
            existing_obj = self.get_storage_object(user_id, collection_name, object_id)

            # Check optimistic concurrency control (Requirements 5.1, 5.2, 5.3)
            if if_unmodified_since is not None:
                existing_modified_ts = existing_obj.modified.timestamp()

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
            if if_unmodified_since is not None and if_unmodified_since != 0:
                # Can't check precondition on non-existent object
                raise PreconditionFailedException(
                    f"Object '{object_id}' does not exist, cannot check precondition"
                )
            # For new objects, create with default values
            existing_obj = BasicStorageObject(
                id=object_id,
                payload="",
                modified=datetime.fromtimestamp(0, tz=timezone.utc),
                sortindex=None,
                ttl=None,
            )

        modified_timestamp = get_current_timestamp()
        modified = datetime.fromtimestamp(modified_timestamp, tz=timezone.utc)

        # Update provided fields
        payload = kwargs.get("payload", existing_obj.payload)
        sortindex = kwargs.get("sortindex", existing_obj.sortindex)
        ttl = kwargs.get("ttl", existing_obj.ttl)

        obj = BasicStorageObject(
            id=object_id,
            payload=payload,
            modified=modified,
            sortindex=sortindex,
            ttl=ttl,
        )
        self.table.put_item(
            Item=self._encode_basic_storage_object(
                user_id=user_id, collection_name=collection_name, obj=obj
            )
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

        # Verify collection exists
        self.get_collection(user_id, collection_name)

        modified = get_current_timestamp()
        pk = self._collection_pk(user_id, collection_name)

        # Delete each specified object
        for object_id in ids:
            try:
                self.table.delete_item(
                    Key={
                        "PK": pk,
                        "SK": self._object_sk(object_id),
                    },
                )
            except Exception:
                # Continue deleting other objects even if one fails
                pass

        # Update collection's last-modified time
        collection = self.get_collection(user_id, collection_name)
        modified_dt = datetime.fromtimestamp(modified, tz=timezone.utc)
        collection_data = CollectionData(
            name=collection_name,
            modified=modified_dt,
            count=collection.count,  # Count will be updated separately if needed
            usage=collection.usage,  # Usage will be updated separately if needed
        )
        metadata_item = self._encode_collection_data(user_id, collection_data)
        self.table.put_item(Item=metadata_item)

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
