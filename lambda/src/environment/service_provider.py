import os
from functools import cached_property

import boto3
from aws_lambda_powertools.event_handler import CORSConfig

from src.routes.bso.delete import DeleteBSORoute
from src.routes.bso.read import ReadBSORoute
from src.routes.bso.update import UpdateBSORoute
from src.routes.collections.create import CreateCollectionRoute
from src.routes.collections.delete import DeleteCollectionRoute
from src.routes.collections.list import ListCollectionsRoute
from src.routes.collections.read import ReadCollectionRoute
from src.routes.collections.update import UpdateCollectionRoute
from src.routes.info.read_collections import ReadCollectionsInfoRoute
from src.routes.info.read_configuration import ReadConfigurationRoute
from src.routes.info.read_counts import ReadCollectionCountsRoute
from src.routes.info.read_quota import ReadQuotaInfoRoute
from src.routes.info.read_usage import ReadCollectionUsageRoute
from src.routes.storage.delete_all import DeleteAllStorageRoute
from src.routes.storage.delete_root import DeleteAllRootRoute
from src.routes.token.request import GetTokenRoute
from src.services.api_router import ApiRouter, RequestLoggingMiddleware, WeaveTimestampMiddleware
from src.services.hawk_service import HawkService
from src.services.oidc_validator import OIDCValidator
from src.services.storage_manager import StorageManager
from src.services.token_generator import TokenGenerator
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
    def token_users_table_name(self):
        return os.environ.get("TOKEN_USERS_TABLE_NAME")

    @cached_property
    def token_users_table(self):
        """Create DynamoDB Table resource for token users"""
        resource = self.session.resource("dynamodb")
        return resource.Table(self.token_users_table_name)

    @cached_property
    def user_manager(self) -> UserManager:
        return UserManager(table=self.token_users_table)

    @cached_property
    def storage_api_router(self):
        return ApiRouter(
            routes=[
                DeleteAllRootRoute(self.storage_manager),
                DeleteAllStorageRoute(self.storage_manager),
                ReadConfigurationRoute(),
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
            ],
            middlewares=[RequestLoggingMiddleware(), WeaveTimestampMiddleware()],
        )

    # Token API properties

    @cached_property
    def oidc_provider_url(self) -> str:
        return os.environ["OIDC_PROVIDER_URL"]

    @cached_property
    def oidc_client_id(self) -> str:
        return os.environ["OIDC_CLIENT_ID"]

    @cached_property
    def base_domain(self):
        return os.environ.get("BASE_DOMAIN")

    @cached_property
    def storage_domain(self) -> str:
        return f"storage.{self.base_domain}"

    @cached_property
    def clock_skew_tolerance(self) -> int:
        """
        Get clock skew tolerance in seconds for OIDC JWT validation
        """
        return int(os.environ["CLOCK_SKEW_TOLERANCE"])

    @cached_property
    def oidc_cache_ttl_seconds(self) -> int:
        """
        Get OIDC configuration cache TTL in seconds (default 3600 / 1 hour)
        """
        return int(os.environ.get("OIDC_CACHE_TTL_SECONDS", "3600"))

    @cached_property
    def hawk_timestamp_skew_tolerance(self) -> int:
        """
        Get HAWK timestamp skew tolerance in seconds

        Separate from OIDC clock_skew_tolerance to allow independent configuration
        of HAWK timestamp validation vs OIDC JWT validation
        """
        return int(os.environ["HAWK_TIMESTAMP_SKEW_TOLERANCE"])

    @cached_property
    def retry_after_seconds(self) -> int:
        """Get Retry-After value for 503 responses in seconds (default 30)"""
        return int(os.environ["RETRY_AFTER_SECONDS"])

    @cached_property
    def oidc_validator(self) -> OIDCValidator:
        """Create OIDC validator with configuration from environment variables"""
        return OIDCValidator(
            provider_url=self.oidc_provider_url,
            client_id=self.oidc_client_id,
            clock_skew_tolerance=self.clock_skew_tolerance,
            cache_ttl_seconds=self.oidc_cache_ttl_seconds,
        )

    @cached_property
    def token_generator(self) -> TokenGenerator:
        """Create token generator with base URL from environment"""
        return TokenGenerator(storage_domain=self.storage_domain, hawk_service=self.hawk_service)

    @cached_property
    def token_api_router(self):
        """Create API router for Token API with RequestTokenRoute"""
        cors = CORSConfig(
            allow_origin=f"https://{self.base_domain}",
            allow_headers=["Authorization", "Content-Type", "X-Client-State"],
            max_age=3600,
        )
        return ApiRouter(
            routes=[
                GetTokenRoute(
                    oidc_validator=self.oidc_validator,
                    user_manager=self.user_manager,
                    token_generator=self.token_generator,
                    retry_after_seconds=self.retry_after_seconds,
                ),
            ],
            middlewares=[WeaveTimestampMiddleware()],
            cors=cors,
        )

    # HAWK Authorizer properties

    @cached_property
    def token_cache_table_name(self):
        return os.environ.get("TOKEN_CACHE_TABLE_NAME")

    @cached_property
    def token_duration(self) -> int:
        return int(os.environ["TOKEN_DURATION"])

    @cached_property
    def token_cache_table(self):
        """Create DynamoDB Table resource for token cache"""
        resource = self.session.resource("dynamodb")
        return resource.Table(self.token_cache_table_name)

    @cached_property
    def hawk_service(self) -> HawkService:
        """Create HAWK service for authentication"""
        return HawkService(
            token_cache_table=self.token_cache_table,
            timestamp_skew_tolerance=self.hawk_timestamp_skew_tolerance,
            token_duration=self.token_duration,
        )
