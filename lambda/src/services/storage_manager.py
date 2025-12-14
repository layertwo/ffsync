"""Storage manager for DynamoDB operations"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from botocore.exceptions import ClientError

from src.shared.exceptions import (
    CollectionNotFoundException,
    StorageObjectNotFoundException,
)
from src.shared.models import (
    BasicStorageObject,
    BatchResult,
    CollectionData,
    get_current_timestamp,
)

_PK = "PK"
_SK = "SK"


class StorageManager:
    """Manages storage operations with DynamoDB"""

    def __init__(self, table):
        """Initialize StorageManager

        Args:
            table: DynamoDB Table resource
        """
        self.table = table

    def _collection_pk(self, collection_name: str) -> str:
        """Generate partition key for collection"""
        return f"COLLECTION#{collection_name}"

    def _metadata_sk(self) -> str:
        """Generate sort key for collection metadata"""
        return "METADATA"

    def _object_sk(self, object_id: str) -> str:
        """Generate sort key for storage object"""
        return f"OBJECT#{object_id}"

    def _encode_basic_storage_object(self, collection_name: str, obj: BasicStorageObject) -> dict:
        """Encode BasicStorageObject to DynamoDB format"""
        obj_data = obj.to_dict()
        obj_data[_PK] = self._collection_pk(collection_name)
        obj_data[_SK] = self._object_sk(obj.id)
        return obj_data

    def _encode_collection_data(self, collection_data: CollectionData) -> dict:
        """Encode CollectionData to DynamoDB format"""
        col_data = collection_data.to_dict()
        col_data[_PK] = self._collection_pk(collection_data.name)
        col_data[_SK] = self._metadata_sk()
        return col_data

    def get_collection(self, collection_name: str) -> CollectionData:
        """Get collection metadata

        Args:
            collection_name: Name of the collection

        Returns:
            CollectionData object

        Raises:
            CollectionNotFoundException: If collection doesn't exist
        """
        try:
            response = self.table.get_item(
                Key={
                    "PK": {"S": self._collection_pk(collection_name)},
                    "SK": {"S": self._metadata_sk()},
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

    def get_storage_object(self, collection_name: str, object_id: str) -> BasicStorageObject:
        """Get a storage object

        Args:
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
                    "PK": {"S": self._collection_pk(collection_name)},
                    "SK": {"S": self._object_sk(object_id)},
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
        self, collection_name: str, objects: Optional[List[BasicStorageObject]] = None
    ) -> tuple[CollectionData, BatchResult]:
        """Create or update a collection

        Args:
            collection_name: Name of the collection
            objects: Optional list of objects to add

        Returns:
            Tuple of (CollectionData, BatchResult)
        """
        modified_timestamp = get_current_timestamp()
        modified = datetime.fromtimestamp(modified_timestamp, tz=timezone.utc)
        objects = objects or []

        # Calculate usage
        usage = sum(len(obj.payload) for obj in objects)
        count = len(objects)

        # Create/update collection metadata
        collection_data = CollectionData(
            name=collection_name, modified=modified, count=count, usage=usage
        )
        metadata_item = self._encode_collection_data(collection_data)

        self.table.put_item(Item=metadata_item)

        # Add objects if provided
        success = []
        failed = {}

        if objects:
            for obj in objects:
                try:
                    # Create object with updated timestamp
                    updated_obj = BasicStorageObject(
                        id=obj.id,
                        payload=obj.payload,
                        modified=modified,
                        sortindex=obj.sortindex,
                        ttl=obj.ttl,
                    )
                    obj_item = self._encode_basic_storage_object(collection_name, updated_obj)

                    self.table.put_item(Item=obj_item)
                    success.append(obj.id)
                except Exception as e:
                    failed[obj.id] = [str(e)]

        batch_result = BatchResult(success=success, failed=failed, modified=modified)

        return collection_data, batch_result

    def update_collection(
        self,
        collection_name: str,
        objects: List[BasicStorageObject],
        if_unmodified_since: Optional[float] = None,
    ) -> tuple[CollectionData, BatchResult]:
        """Update a collection

        Args:
            collection_name: Name of the collection
            objects: List of objects to update

        Returns:
            Tuple of (CollectionData, BatchResult)
        """
        modified_timestamp = get_current_timestamp()
        modified = datetime.fromtimestamp(modified_timestamp, tz=timezone.utc)

        # Get current collection metadata
        try:
            collection = self.get_collection(collection_name)
        except CollectionNotFoundException:
            raise

        # Update objects
        success = []
        failed = {}

        for obj in objects:
            try:
                # Create object with updated timestamp
                updated_obj = BasicStorageObject(
                    id=obj.id,
                    payload=obj.payload,
                    modified=modified,
                    sortindex=obj.sortindex,
                    ttl=obj.ttl,
                )
                obj_item = self._encode_basic_storage_object(collection_name, updated_obj)

                self.table.put_item(Item=obj_item)
                success.append(obj.id)
            except Exception as e:
                failed[obj.id] = [str(e)]

        # Update collection metadata
        usage_delta = sum(len(obj.payload) for obj in objects if obj.id in success)
        new_usage = collection.usage + usage_delta
        new_count = collection.count + len(success)

        collection_data = CollectionData(
            name=collection_name, modified=modified, count=new_count, usage=new_usage
        )
        metadata_item = self._encode_collection_data(collection_data)

        self.table.put_item(Item=metadata_item)

        batch_result = BatchResult(success=success, failed=failed, modified=modified)

        return collection_data, batch_result

    def delete_collection(self, collection_name: str) -> float:
        """Delete a collection

        Args:
            collection_name: Name of the collection

        Returns:
            Modified timestamp

        Raises:
            CollectionNotFoundException: If collection doesn't exist
        """
        # Verify collection exists
        self.get_collection(collection_name)

        modified = get_current_timestamp()
        pk = self._collection_pk(collection_name)

        # Query all items in the collection
        response = self.table.query(
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": {"S": pk}},
        )

        # Delete all items
        for item in response.get("Items", []):
            self.table.delete_item(
                Key={"PK": item["PK"], "SK": item["SK"]},
            )

        return modified

    def list_collections(self) -> List[CollectionData]:
        """List all collections

        Returns:
            List of CollectionData objects
        """
        collections = []

        # Scan for all metadata items
        response = self.table.scan(
            FilterExpression="SK = :metadata",
            ExpressionAttributeValues={":metadata": {"S": self._metadata_sk()}},
        )

        for item in response.get("Items", []):
            collection = CollectionData.from_dict(item)
            collections.append(collection)

        return collections

    def get_collection_objects(
        self,
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
        """
        pk = self._collection_pk(collection_name)

        # Query all objects in collection
        response = self.table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :obj_prefix)",
            ExpressionAttributeValues={
                ":pk": {"S": pk},
                ":obj_prefix": {"S": "OBJECT#"},
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
        self, collection_name: str, object_id: str, **kwargs
    ) -> BasicStorageObject:
        """Update a storage object

        Args:
            collection_name: Name of the collection
            object_id: ID of the object
            **kwargs: Fields to update

        Returns:
            Updated BasicStorageObject

        Raises:
            StorageObjectNotFoundException: If object doesn't exist
        """
        # Get existing object to verify it exists
        existing_obj = self.get_storage_object(collection_name, object_id)

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
            Item=self._encode_basic_storage_object(collection_name=collection_name, obj=obj)
        )
        return obj

    def delete_storage_object(self, collection_name: str, object_id: str) -> float:
        """Delete a storage object

        Args:
            collection_name: Name of the collection
            object_id: ID of the object

        Returns:
            Modified timestamp

        Raises:
            StorageObjectNotFoundException: If object doesn't exist
        """
        # Verify object exists
        self.get_storage_object(collection_name, object_id)

        modified = get_current_timestamp()

        self.table.delete_item(
            Key={
                "PK": {"S": self._collection_pk(collection_name)},
                "SK": {"S": self._object_sk(object_id)},
            },
        )

        return modified
