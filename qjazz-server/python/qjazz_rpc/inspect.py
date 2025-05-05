""" Utilities for inspecting cache and catalog objects

    Initialize cache manager and catalog from local
    configuration

    Used a debugging tools inside containers
"""
from functools import cached_property
from pathlib import Path
from typing import (
    Optional,
    Protocol,
    cast,
)

from qjazz_ogc import Catalog, CatalogItem

from qjazz_cache.prelude import (
    CacheEntry,
    CacheManager,
    CheckoutStatus,
    ProjectMetadata,
)
from qjazz_contrib.core import logger
from qjazz_contrib.core.qgis import current_qgis_application, init_qgis_application

from .main import WORKER_SECTION, WorkerConfig


class ConfigProto(Protocol):
    worker: WorkerConfig


def load_config(path: Optional[Path|str], **kwds) -> WorkerConfig:
    """
    """
    from qjazz_contrib.core import config

    confservice = config.ConfBuilder()
    confservice.add_section(WORKER_SECTION, WorkerConfig)

    conf = config.read_config_toml(Path(path), **kwds) if path else {}
    return cast(ConfigProto, confservice.validate(conf)).worker


def init_cache(conf: WorkerConfig) -> CacheManager:

    CacheManager.initialize_handlers(conf.qgis.projects)

    cm = CacheManager(conf.qgis.projects)
    cm.register_as_service()

    return cm


class Inspect:
    def __init__(self, path: Optional[Path|str], **kwds):
        self.conf = load_config(path, **kwds)
        self.catalog = Catalog()

    @property
    def qapp(self):
        return current_qgis_application()

    @cached_property
    def cache(self):
        return init_cache(self.conf)

    def update_catalog(self, prefix: Optional[str] = None) -> Catalog:
        cat = self.catalog
        cat.update(self.cache, not self.conf.qgis.load_project_on_request, prefix=prefix)
        return cat

    def get_catalog_item(self, resource: str) -> Optional[CatalogItem]:
        return self.catalog.get_and_update(self.cache, resource)

    def checkout_project(
        self, loc: str,
        *,
        pull: bool = False,
    ) -> tuple[CacheEntry | ProjectMetadata, CheckoutStatus]:
        cm = self.cache
        url = cm.resolve_path(loc)
        md, status = cm.checkout(url)
        return cm.update(md, status) if pull else (md, status)


def init(
    config_path: Optional[Path],
    log_level: logger.LogLevel = logger.LogLevel.DEBUG,
    **kwds,
) -> Inspect:

    logger.setup_log_handler(log_level)
    init_qgis_application()
    return Inspect(config_path)
