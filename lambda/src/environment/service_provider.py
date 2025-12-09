import os
from functools import cached_property

import boto3

from src.routes.bso.delete import DeleteBSORoute
from src.routes.bso.read import ReadBSORoute
from src.routes.bso.update import UpdateBSORoute
from src.routes.collections.create import CreateCollectionRoute
from src.routes.collections.delete import DeleteCollectionRoute
from src.routes.collections.list import ListCollectionsRoute
from src.routes.collections.read import ReadCollectionRoute
from src.routes.collections.update import UpdateCollectionRoute
from src.routes.info.read_collections import ReadCollectionsInfoRoute
from src.routes.info.read_counts import ReadCollectionCountsRoute
from src.routes.info.read_quota import ReadQuotaInfoRoute
from src.routes.info.read_usage import ReadCollectionUsageRoute
from src.routes.storage.delete_all import DeleteAllStorageRoute
from src.services.api_router import ApiRouter
from src.services.storage_manager import StorageManager
from src.services.user_manager import UserManager


class ServiceProvider:
    @cached_property
    def aws_region(self):  # pragma: nocover
        return os.environ.get("AWS_REGION")

    @cached_property
    def session(self):  # pragma: nocover
        return boto3.Session(region_name=self.aws_region)

    @cached_property
    def table_name(self):
        return os.environ.get("STORAGE_TABLE_NAME")

    @cached_property
    def dynamodb_table(self):
        """Create DynamoDB Table resource"""
        resource = self.session.resource("dynamodb")
        return resource.Table(self.table_name)

    @cached_property
    def storage_manager(self) -> StorageManager:
        return StorageManager(table=self.dynamodb_table)

    @cached_property
    def token_users_table_name(self):  # pragma: nocover
        return os.environ.get("TOKEN_USERS_TABLE_NAME")

    @cached_property
    def token_users_table(self):  # pragma: nocover
        """Create DynamoDB Table resource for token users"""
        resource = self.session.resource("dynamodb")
        return resource.Table(self.token_users_table_name)

    @cached_property
    def user_manager(self) -> UserManager:  # pragma: nocover
        return UserManager(table=self.token_users_table)

    @cached_property
    def storage_api_router(self):
        return ApiRouter(
            routes=[
                DeleteAllStorageRoute(),
                ReadCollectionsInfoRoute(self.storage_manager),
                ReadCollectionCountsRoute(self.storage_manager),
                ReadCollectionUsageRoute(self.storage_manager),
                ReadQuotaInfoRoute(self.storage_manager),
                ListCollectionsRoute(self.storage_manager),
                CreateCollectionRoute(self.storage_manager),
                ReadCollectionRoute(self.storage_manager),
                UpdateCollectionRoute(self.storage_manager),
                DeleteCollectionRoute(self.storage_manager),
                ReadBSORoute(self.storage_manager),
                UpdateBSORoute(self.storage_manager),
                DeleteBSORoute(self.storage_manager),
            ]
        )
