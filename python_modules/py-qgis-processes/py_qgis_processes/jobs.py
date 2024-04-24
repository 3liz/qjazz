#
# Processing worker
#
import os

from functools import cached_property

from pydantic import JsonValue
from typing_extensions import Dict, List, Self

from py_qgis_cache import (
    CacheManager,
)
from py_qgis_contrib.core import logger
from py_qgis_contrib.core.componentmanager import FactoryNotFoundError
from py_qgis_contrib.core.qgis import (
    PluginType,
    QgisPluginService,
    init_qgis_application,
    init_qgis_processing,
    qgis_initialized,
    show_all_versions,
    show_qgis_settings,
)
from py_qgis_processes_schemas import ProcessesSummary

from .celery import JobContext, Worker


class QgisContext:
    """Qgis context initializer
    """
    def __init__(self, ctx: JobContext):
        self._ctx = ctx

    def setup(self):
        if not qgis_initialized():
            verbose = logger.isEnabledFor(logger.LogLevel.DEBUG)
            if verbose:
                os.environ['QGIS_DEBUG'] = '1'
            init_qgis_application()
            if verbose:
                logger.debug(show_qgis_settings())  # noqa T201

    def __enter__(self) -> Self:
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @cached_property
    def cache(self) -> CacheManager:
        try:
            cm = CacheManager.get_service()
        except FactoryNotFoundError:
            CacheManager.initialize_handlers()
            cm = CacheManager(self._ctx.processing.projects)
            cm.register_as_service()
        return cm

    @cached_property
    def init_processing(self):
        try:
            plugin_s = QgisPluginService.get_service()
        except FactoryNotFoundError:
            init_qgis_processing()
            # Load plugins
            plugin_s = QgisPluginService(self._ctx.processing.plugins)
            plugin_s.load_plugins(PluginType.PROCESSING)
            plugin_s.register_as_service()
        return plugin_s


app = Worker()


@app.job(name="list_processes", run_context=True)
def list_processes(ctx: JobContext, /) -> List[ProcessesSummary]:
    """Return the list of processes
    """
    return []


@app.job(name="env", run_context=True)
def env(ctx: JobContext, /) -> Dict[str, JsonValue]:
    """Return execution environnement"""
    with QgisContext(ctx):
        from qgis.core import Qgis
        return dict(
            qgis_version=Qgis.QGIS_VERSION_INT,
            qgis_release=Qgis.QGIS_RELEASE_NAME,
            versions=list(show_all_versions()),
            environment=dict(os.environ),
        )
