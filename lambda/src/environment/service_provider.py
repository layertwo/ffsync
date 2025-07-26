from functools import cached_property

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


class ServiceProvider:

    @cached_property
    def api_router(self):
        return ApiRouter(
            routes=[
                DeleteAllStorageRoute(),
                ReadCollectionsInfoRoute(),
                ReadCollectionCountsRoute(),
                ReadCollectionUsageRoute(),
                ReadQuotaInfoRoute(),
                ListCollectionsRoute(),
                CreateCollectionRoute(),
                ReadCollectionRoute(),
                UpdateCollectionRoute(),
                DeleteCollectionRoute(),
                ReadBSORoute(),
                UpdateBSORoute(),
                DeleteBSORoute(),
            ]
        )
