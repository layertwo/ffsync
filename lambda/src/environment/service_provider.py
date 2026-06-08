import functools
import json
import os
from functools import cached_property

import boto3
from aws_lambda_powertools.event_handler import CORSConfig, Response
from aws_lambda_powertools.logging import Logger
from aws_lambda_powertools.metrics import Metrics

from src.middlewares.hawk_auth import HawkAuthenticationError, HawkAuthMiddleware, UidMismatchError
from src.middlewares.request_logging import RequestLoggingMiddleware
from src.middlewares.weave_timestamp import WeaveTimestampMiddleware
from src.routes.auth.account_attached_clients import AccountAttachedClientsRoute
from src.routes.auth.account_create import AccountCreateRoute
from src.routes.auth.account_device import AccountDeviceRoute
from src.routes.auth.account_devices import AccountDevicesRoute
from src.routes.auth.account_devices_notify import AccountDevicesNotifyRoute
from src.routes.auth.account_keys import AccountKeysRoute
from src.routes.auth.account_login import AccountLoginRoute
from src.routes.auth.account_status import AccountStatusRoute
from src.routes.auth.jwks import JWKSRoute
from src.routes.auth.oauth_authorization import OAuthAuthorizationRoute
from src.routes.auth.oauth_destroy import OAuthDestroyRoute
from src.routes.auth.oauth_token import OAuthTokenRoute
from src.routes.auth.oidc_discovery import OIDCDiscoveryRoute
from src.routes.auth.oidc_exchange import OIDCCodeExchangeRoute, OIDCProviderConfigRoute
from src.routes.auth.scoped_key_data import ScopedKeyDataRoute
from src.routes.auth.session_destroy import SessionDestroyRoute
from src.routes.auth.session_status import SessionStatusRoute
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
from src.routes.profile.get_profile import GetProfileRoute
from src.routes.storage.delete_all import DeleteAllStorageRoute
from src.routes.storage.delete_root import DeleteAllRootRoute
from src.routes.token.request import GetTokenRoute
from src.services.api_router import ApiRouter
from src.services.auth_account_manager import AuthAccountManager
from src.services.channel_service import ChannelService
from src.services.device_manager import DeviceManager
from src.services.fxa_token_manager import FxATokenManager
from src.services.hawk_service import HawkService
from src.services.jwt_service import JWTService
from src.services.jwt_verifier import JWTVerifier
from src.services.oauth_code_manager import OAuthCodeManager
from src.services.oidc_validator import OIDCValidator
from src.services.storage_manager import StorageManager
from src.services.token_generator import TokenGenerator
from src.services.user_manager import UserManager


@functools.lru_cache(maxsize=1)
def create_service_provider() -> "ServiceProvider":  # pragma: nocover
    """Create a cached ServiceProvider singleton.

    Uses lru_cache so the same instance is reused across warm Lambda invocations.
    In tests, pass service_provider directly to bypass this.
    """
    return ServiceProvider()


def lambda_entrypoint(fn):
    """Decorator that injects a cached ServiceProvider when none is provided.

    In production, creates/reuses a cached ServiceProvider via lru_cache.
    In tests, pass service_provider directly to inject a mock.
    """

    @functools.wraps(fn)
    def wrapper(event, context, service_provider=None):
        if service_provider is None:  # pragma: nocover
            service_provider = create_service_provider()
        try:
            return fn(event, context, service_provider)
        finally:
            service_provider.metrics.flush_metrics()

    return wrapper


logger = Logger()


class ServiceProvider:
    @cached_property
    def metrics(self) -> Metrics:
        return Metrics(namespace="ffsync")

    @cached_property
    def user_agent(self) -> str:
        return "layertwo-ffsync/1.0"

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
    def dynamodb_resource(self):  # pragma: nocover
        """Shared DynamoDB resource — reuses a single connection pool."""
        return self.session.resource("dynamodb")

    @cached_property
    def dynamodb_table(self):
        """Create DynamoDB Table resource"""
        return self.dynamodb_resource.Table(self.table_name)

    @cached_property
    def storage_manager(self) -> StorageManager:
        return StorageManager(table=self.dynamodb_table)

    @cached_property
    def token_users_table_name(self):
        return os.environ.get("TOKEN_USERS_TABLE_NAME")

    @cached_property
    def token_users_table(self):
        """Create DynamoDB Table resource for token users"""
        return self.dynamodb_resource.Table(self.token_users_table_name)

    @cached_property
    def user_manager(self) -> UserManager:
        return UserManager(table=self.token_users_table)

    @cached_property
    def _storage_exception_handlers(self) -> dict:
        def handle_hawk_auth(ex):
            return Response(
                status_code=401,
                content_type="application/json",
                body='{"error": "Unauthorized"}',
            )

        def handle_uid_mismatch(ex):
            return Response(
                status_code=403,
                content_type="application/json",
                body='{"error": "uid mismatch"}',
            )

        return {
            HawkAuthenticationError: handle_hawk_auth,
            UidMismatchError: handle_uid_mismatch,
        }

    @cached_property
    def _auth_exception_handlers(self) -> dict:
        def handle_hawk_auth(ex):
            return Response(
                status_code=401,
                content_type="application/json",
                body=json.dumps({"code": 401, "errno": 110, "message": str(ex)}),
            )

        return {
            HawkAuthenticationError: handle_hawk_auth,
        }

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
            middlewares=[
                RequestLoggingMiddleware(),
                HawkAuthMiddleware(hawk_service=self.hawk_service, metrics=self.metrics),
                WeaveTimestampMiddleware(),
            ],
            exception_handlers=self._storage_exception_handlers,
            enable_validation=True,
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
            user_agent=self.user_agent,
            metrics=self.metrics,
        )

    @cached_property
    def token_generator(self) -> TokenGenerator:
        """Create token generator with base URL from environment"""
        return TokenGenerator(storage_domain=self.storage_domain, hawk_service=self.hawk_service)

    # Auth API properties

    @cached_property
    def auth_table_name(self):
        return os.environ.get("AUTH_TABLE_NAME")

    @cached_property
    def auth_table(self):
        """DynamoDB Table for auth accounts, sessions, and OAuth codes"""
        return self.dynamodb_resource.Table(self.auth_table_name)

    @cached_property
    def auth_signing_key_id(self) -> str:
        return os.environ["AUTH_SIGNING_KEY_ID"]

    @cached_property
    def kms_client(self):  # pragma: nocover
        return self.session.client("kms")

    @cached_property
    def auth_account_manager(self) -> AuthAccountManager:
        return AuthAccountManager(table=self.auth_table)

    @cached_property
    def device_manager(self) -> DeviceManager:
        return DeviceManager(table=self.auth_table)

    @cached_property
    def fxa_token_manager(self) -> FxATokenManager:
        return FxATokenManager(table=self.auth_table, metrics=self.metrics)

    @cached_property
    def oauth_code_manager(self) -> OAuthCodeManager:
        return OAuthCodeManager(table=self.auth_table)

    @cached_property
    def jwt_service(self) -> JWTService:
        return JWTService(
            kms_client=self.kms_client,
            signing_key_id=self.auth_signing_key_id,
            issuer=f"https://auth.{self.base_domain}",
        )

    @cached_property
    def jwt_verifier(self) -> JWTVerifier:
        return JWTVerifier(jwt_service=self.jwt_service)

    @cached_property
    def session_hawk_middleware(self) -> HawkAuthMiddleware:
        return HawkAuthMiddleware(token_manager=self.fxa_token_manager, metrics=self.metrics)

    @cached_property
    def cors_config(self) -> CORSConfig:
        return CORSConfig(
            allow_origin=f"https://{self.base_domain}",
            allow_headers=["Authorization", "Content-Type", "X-Client-State"],
            max_age=3600,
        )

    @cached_property
    def auth_api_router(self):
        """Create API router for Auth API with all FxA-compatible routes"""
        return ApiRouter(
            routes=[
                # Account routes
                AccountStatusRoute(account_manager=self.auth_account_manager),
                AccountCreateRoute(
                    account_manager=self.auth_account_manager,
                    token_manager=self.fxa_token_manager,
                    oidc_validator=self.oidc_validator,
                ),
                AccountLoginRoute(
                    account_manager=self.auth_account_manager,
                    token_manager=self.fxa_token_manager,
                ),
                AccountKeysRoute(
                    account_manager=self.auth_account_manager,
                    token_manager=self.fxa_token_manager,
                ),
                ScopedKeyDataRoute(
                    account_manager=self.auth_account_manager,
                    middlewares=[self.session_hawk_middleware],
                ),
                # Session routes
                SessionStatusRoute(middlewares=[self.session_hawk_middleware]),
                SessionDestroyRoute(
                    token_manager=self.fxa_token_manager,
                    middlewares=[self.session_hawk_middleware],
                ),
                # OAuth routes
                OAuthAuthorizationRoute(
                    oauth_code_manager=self.oauth_code_manager,
                    middlewares=[self.session_hawk_middleware],
                ),
                OAuthTokenRoute(
                    oauth_code_manager=self.oauth_code_manager,
                    jwt_service=self.jwt_service,
                    account_manager=self.auth_account_manager,
                    token_manager=self.fxa_token_manager,
                    metrics=self.metrics,
                ),
                OAuthDestroyRoute(oauth_code_manager=self.oauth_code_manager),
                # Discovery routes
                OIDCDiscoveryRoute(jwt_service=self.jwt_service),
                JWKSRoute(jwt_service=self.jwt_service),
                # OIDC proxy routes (server-side token exchange)
                OIDCProviderConfigRoute(oidc_validator=self.oidc_validator),
                OIDCCodeExchangeRoute(
                    oidc_validator=self.oidc_validator,
                    account_manager=self.auth_account_manager,
                    user_agent=self.user_agent,
                    metrics=self.metrics,
                ),
                # Device management routes
                AccountDeviceRoute(
                    device_manager=self.device_manager,
                    middlewares=[self.session_hawk_middleware],
                ),
                AccountDevicesRoute(
                    device_manager=self.device_manager,
                    middlewares=[self.session_hawk_middleware],
                ),
                AccountAttachedClientsRoute(
                    device_manager=self.device_manager,
                    middlewares=[self.session_hawk_middleware],
                ),
                AccountDevicesNotifyRoute(
                    middlewares=[self.session_hawk_middleware],
                ),
            ],
            middlewares=[WeaveTimestampMiddleware()],
            cors=self.cors_config,
            exception_handlers=self._auth_exception_handlers,
            enable_validation=True,
        )

    @cached_property
    def token_api_router(self):
        """Create API router for Token API (sync token issuance)"""
        return ApiRouter(
            routes=[
                GetTokenRoute(
                    oidc_validator=self.jwt_verifier,
                    user_manager=self.user_manager,
                    token_generator=self.token_generator,
                    retry_after_seconds=self.retry_after_seconds,
                    metrics=self.metrics,
                ),
            ],
            middlewares=[WeaveTimestampMiddleware()],
            cors=self.cors_config,
            enable_validation=True,
        )

    @cached_property
    def profile_api_router(self):
        """Create API router for Profile API (OAuth Bearer auth)"""
        return ApiRouter(
            routes=[
                GetProfileRoute(
                    jwt_verifier=self.jwt_verifier,
                    auth_account_manager=self.auth_account_manager,
                    metrics=self.metrics,
                ),
            ],
            middlewares=[WeaveTimestampMiddleware()],
            cors=self.cors_config,
            enable_validation=True,
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
        return self.dynamodb_resource.Table(self.token_cache_table_name)

    @cached_property
    def hawk_service(self) -> HawkService:
        """Create HAWK service for authentication"""
        return HawkService(
            token_cache_table=self.token_cache_table,
            timestamp_skew_tolerance=self.hawk_timestamp_skew_tolerance,
            token_duration=self.token_duration,
        )

    # Channel Service properties

    @cached_property
    def channel_table_name(self):
        return os.environ.get("CHANNEL_TABLE_NAME")

    @cached_property
    def channel_table(self):
        """DynamoDB Table for pairing channel state"""
        resource = self.session.resource("dynamodb")
        return resource.Table(self.channel_table_name)

    @cached_property
    def channel_service(self) -> ChannelService:
        return ChannelService(table=self.channel_table, session=self.session)
