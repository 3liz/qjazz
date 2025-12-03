import os
import traceback

from dataclasses import dataclass
from enum import Flag
from pathlib import PurePosixPath
from typing import (
    Iterator,
    Optional,
    Self,
    cast,
)
from urllib.parse import urlsplit

from qgis.core import (
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)

from qjazz_cache.prelude import (
    CacheEntry,
    CacheManager,
    CheckoutStatus,
    ProjectMetadata,
    ProtocolHandler,
    ResourceNotAllowed,
)
from qjazz_core import componentmanager, logger
from qjazz_core.condition import assert_postcondition

from .project import Collection

Co = CheckoutStatus

CATALOG_CONTRACTID = "@3liz.org/catalog;1"

QJAZZ_CATALOG_MIN_QGIS_VERSION = (3, 0)


class OgcEndpoints(Flag):
    NONE = 0x00
    MAP = 0x01
    FEATURES = 0x02
    COVERAGE = 0x04
    TILE = 0x08


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
    layers: dict[str, OgcEndpoints]
    coll: Collection
    location: PurePosixPath


def get_pinned_project(md: ProjectMetadata, cm: CacheManager) -> Optional[CacheEntry]:
    """Return a pinned project cache entry"""
    entry, co_status = cm.checkout(urlsplit(md.uri))
    match co_status:
        case Co.UNCHANGED | Co.UPDATED | Co.NEEDUPDATE:
            entry = cast("CacheEntry", entry)
            if entry.pinned:
                return entry
            return None
        case _:
            return None


def get_minimum_qgis_version():
    ver = os.getenv("QJAZZ_CATALOG_MIN_QGIS_VERSION")
    if ver:
        from pydantic import TypeAdapter, ValidationError

        try:
            return TypeAdapter(tuple[int, int]).validate_python(ver.split(".")[:2])
        except ValidationError:
            logger.error("Invalid value for QJAZZ_CATALOG_MIN_QGIS_VERSION: '%s'", ver)

    return QJAZZ_CATALOG_MIN_QGIS_VERSION


class ProjectTooOld(Exception):
    pass


class Catalog:
    """Handle Qgis project's catalog"""

    def __init__(self) -> None:
        self._catalog: dict[str, CatalogItem] = {}
        self._schema = Collection.model_json_schema()
        self._minimum_qgis_version = get_minimum_qgis_version()

    def update_items(
        self,
        cm: CacheManager,
        pinned: bool = False,
        *,
        prefix: Optional[str] = None,
    ) -> Iterator[CatalogItem]:
        catalog = self._catalog

        # Iterate over the whole catalog
        loader_config = FastLoaderConfig()
        for md, public_path, handler, location in cm.collect_projects_ex(prefix):
            if pinned and not get_pinned_project(md, cm):
                # Handle only pinned projects
                continue

            public_path = public_path.removesuffix(".qgs").removesuffix(".qgz")
            item = catalog.get(public_path)

            if not item or md.last_modified > item.md.last_modified:
                try:
                    item = new_catalog_item(
                        md,
                        public_path,
                        handler,
                        location,
                        loader_config,
                        self._minimum_qgis_version,
                    )
                except Exception:
                    logger.error(
                        "Error loading project snapshot %s\n%s",
                        md.uri,
                        traceback.format_exc(),
                    )
                    continue

            yield item

    def update(self, cm: CacheManager, pinned: bool = False, *, prefix: Optional[str] = None):
        self._catalog = {
            item.public_path: item
            for item in self.update_items(
                cm,
                pinned,
                prefix=prefix,
            )
        }

    def get_and_update(
        self,
        cm: CacheManager,
        ident: str,
        *,
        pinned: bool = False,
    ) -> Optional[CatalogItem]:
        """Fetch a resource in the catalog and update it"""
        item = self._catalog.get(ident)
        if not item:
            try:
                url = cm.resolve_path(ident)
            except ResourceNotAllowed:
                return None

            location = cast("PurePosixPath", cm.find_location(ident))
            assert_postcondition(location is not None)

            md, status = cm.checkout(url)
            match status:
                case Co.UNCHANGED | Co.UPDATED | Co.NEEDUPDATE:
                    entry = cast("CacheEntry", md)
                    if pinned and not entry.pinned:
                        # Handle only pinned items
                        return None
                case CheckoutStatus.REMOVED | CheckoutStatus.NOTFOUND:
                    return None
        else:
            md, status = cm.checkout(urlsplit(item.md.uri))
            if status in (CheckoutStatus.REMOVED, CheckoutStatus.NOTFOUND):
                del self._catalog[ident]
                return None
            if cast("ProjectMetadata", md).last_modified <= item.md.last_modified:
                return item

            location = item.location

        md = cast("ProjectMetadata", md)
        try:
            handler = cm.get_protocol_handler(md.scheme)
            item = new_catalog_item(
                md,
                ident,
                handler,
                location,
                FastLoaderConfig(),
                self._minimum_qgis_version,
            )
            self._catalog[ident] = item
            return item
        except Exception:
            logger.error(
                "Error loading project snapshot %s\n%s",
                md.uri,
                traceback.format_exc(),
            )
        return None

    def iter(self, prefix: Optional[str] = None) -> Iterator[CatalogItem]:
        if prefix:
            for item in self._catalog.values():
                if item.location.is_relative_to(prefix):
                    yield item
        else:
            yield from self._catalog.values()

    def get(self, ident: str) -> Optional[CatalogItem]:
        return self._catalog.get(ident)

    def __len__(self) -> int:
        return len(self._catalog)

    @classmethod
    def get_service(cls) -> Self:
        """Return cache manager as a service.
        This require that register_as_service has been called
        in the current context
        """
        return componentmanager.get_service(CATALOG_CONTRACTID)

    def register_as_service(self):
        componentmanager.register_service(CATALOG_CONTRACTID, self)


#
# Create a new catalog item
#
def new_catalog_item(
    md: ProjectMetadata,
    public_path: str,
    handler: ProtocolHandler,
    location: PurePosixPath,
    loader_config: FastLoaderConfig,
    minimum_qgis_version: tuple[int, int],
) -> CatalogItem:
    logger.debug("=Catalog: updating: '%s'", md.uri)
    project = handler.project(md, loader_config)

    check_project_version(md, project, minimum_qgis_version)

    layers = dict(t for t in collect_layers(project))
    return CatalogItem(
        public_path=public_path,
        md=md,
        layers=layers,
        coll=Collection.from_project(public_path, project),
        location=location,
    )


#
# Collect layer infos
#
def collect_layers(p: QgsProject) -> Iterator[tuple[str, OgcEndpoints]]:
    """Collect layers and corresponding OgcEndpoint"""
    from qgis.server import QgsServerProjectUtils

    from .layers import LayerAccessor

    accessor = LayerAccessor(p)

    wfs_layers_id = set(QgsServerProjectUtils.wfsLayerIds(p))
    wcs_layers_id = set(QgsServerProjectUtils.wcsLayerIds(p))

    # root = project.layerTreeRoot()
    for layer in accessor.layers():
        endpoints = OgcEndpoints.NONE
        match layer:
            case QgsVectorLayer():
                if layer.id() in wfs_layers_id:
                    endpoints |= OgcEndpoints.FEATURES
                # NOTE: on old projects this returns always False
                if layer.isSpatial():
                    endpoints |= OgcEndpoints.MAP
            case QgsRasterLayer():
                endpoints |= OgcEndpoints.MAP
                if layer.id() in wcs_layers_id:
                    endpoints |= OgcEndpoints.COVERAGE

        yield (accessor.layer_name(layer), endpoints)


#
# Check project version
#
def check_project_version(
    md: ProjectMetadata,
    project: QgsProject,
    minimum_qgis_version: tuple[int, int],
):
    project_ver = project.lastSaveVersion()
    if (
        not project_ver.isNull()
        and (
            project_ver.majorVersion(),
            project_ver.minorVersion(),
        )
        < minimum_qgis_version
    ):
        logger.warning("Project %s is too old (%s)", md.uri, project_ver.text())
        raise ProjectTooOld(str(md.uri))
