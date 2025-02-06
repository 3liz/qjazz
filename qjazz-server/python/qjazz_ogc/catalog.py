import traceback

from dataclasses import dataclass
from typing import (
    Dict,
    Iterator,
    Optional,
    Self,
    cast,
)
from urllib.parse import urlsplit

from qjazz_cache.prelude import CacheEntry, CacheManager, CheckoutStatus, ProjectMetadata
from qjazz_cache.storage import load_project_from_uri
from qjazz_contrib.core import componentmanager, logger

from .project import Collection

Co = CheckoutStatus

CATALOG_CONTRACTID = '@3liz.org/catalog;1'


@dataclass(frozen=True)
class FastLoaderConfig:
    trust_layer_metadata: bool = True
    disable_getprint: bool = True
    force_readonly_layers: bool = True
    dont_resolve_layers: bool = True
    disable_advertised_urls: bool = False
    ignore_bad_layers: bool = True


@dataclass
class CatalogItem:
    public_path: str
    md: ProjectMetadata
    coll: Collection


def get_pinned_project(md: ProjectMetadata, cm: CacheManager) -> Optional[CacheEntry]:
    """ Return a pinned project cache entry """
    entry, co_status = cm.checkout(urlsplit(md.uri))
    match co_status:
        case Co.UNCHANGED | Co.UPDATED | Co.NEEDUPDATE:
            entry = cast(CacheEntry, entry)
            if entry.pinned:
                return entry
            else:
                return None
        case _:
            return None


class Catalog:
    """ Handle Qgis project's catalog
    """
    def __init__(self) -> None:
        self._catalog: Dict[str, CatalogItem] = {}
        self._schema = Collection.model_json_schema()

    def update_items(self, cm: CacheManager, pinned: bool = False) -> Iterator[CatalogItem]:

        catalog = self._catalog

        # Iterate over the whole catalog
        loader_config = FastLoaderConfig()
        for md, public_path in cm.collect_projects():

            if pinned and not get_pinned_project(md, cm):
                # Handle only pinned projects
                continue

            public_path = public_path.removesuffix('.qgs').removesuffix('.qgz')
            item = catalog.get(public_path)

            if not item or md.last_modified > item.md.last_modified:
                try:
                    logger.debug("=Catalog: updating: '%s'", md.uri)
                    project = load_project_from_uri(md.uri, loader_config)
                    item = CatalogItem(
                        public_path=public_path,
                        md=md,
                        coll=Collection.from_project(public_path, project),
                    )
                except Exception:
                    logger.error(
                        "Error loading project snapshot:%s\n%s",
                        md.uri,
                        traceback.format_exc(),
                    )
                    continue

            yield item

    def update(self, cm: CacheManager, pinned: bool = False):
        self._catalog = {item.public_path: item for item in self.update_items(cm, pinned)}

    def iter(self) -> Iterator[CatalogItem]:
        yield from self._catalog.values()

    def get(self, ident: str) -> Optional[CatalogItem]:
        return self._catalog.get(ident)

    def __len__(self) -> int:
        return len(self._catalog)

    @classmethod
    def get_service(cls) -> Self:
        """ Return cache manager as a service.
            This require that register_as_service has been called
            in the current context
        """
        return componentmanager.get_service(CATALOG_CONTRACTID)

    def register_as_service(self):
        componentmanager.register_service(CATALOG_CONTRACTID, self)
