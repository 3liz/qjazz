#
# Processing worker
#
import os

from functools import cached_property

from typing_extensions import (
    Callable,
    Optional,
    Self,
)

from qgis.core import QgsProcessingFeedback, QgsProject

from py_qgis_cache import CacheManager
from py_qgis_contrib.core import logger
from py_qgis_contrib.core.componentmanager import FactoryNotFoundError
from py_qgis_contrib.core.qgis import (
    PluginType,
    QgisPluginService,
    init_qgis_application,
    init_qgis_processing,
    qgis_initialized,
    show_qgis_settings,
)

from .celery import JobContext
from .processing import ProcessingConfig

ProgressFun = Callable[[Optional[float], Optional[str]], None]


class FeedBack(QgsProcessingFeedback):

    def __init__(self, progress_fun: ProgressFun):
        super().__init__(False)
        self._progress_msg = ""
        self._progress_fun = progress_fun

        # Connect slot
        self.progressChanged.connect(self._on_progress_changed)

    def __del__(self):
        self.progressChanged.disconnect(self._on_progress_changed)

    def _on_progress_changed(self, progress: float):
        self._progress_fun(progress, self._progress_msg)

    def pushFormattedMessage(html: str, text: str):
        logger.info(text)

    def setProgressText(self, message: str):
        self._progress_msg = message
        self._progress_fun(self.percent(), self._progress_msg)

    def reportError(self, error: str, fatalError: bool = False):
        (logger.critical if fatalError else logger.error)(error)

    def pushInfo(self, info: str) -> None:
        logger.info(info)

    def pushWarning(self, warning: str) -> None:
        logger.warning(warning)

    def pushDebugInfo(self, info: str) -> None:
        logger.debug(info)


class QgisContext:
    """Qgis context initializer
    """
    def __init__(self, ctx: JobContext):
        self._ctx = ctx
        self._conf: ProcessingConfig = ctx.processing_config
        self._setup()

    def _setup(self):
        if not qgis_initialized():
            debug = logger.isEnabledFor(logger.LogLevel.DEBUG)
            if debug:
                os.environ['QGIS_DEBUG'] = '1'

            init_qgis_application(settings=self._conf.settings())
            if debug:
                logger.debug(show_qgis_settings())  # noqa T201

    def __enter__(self) -> Self:
        self.plugins
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @property
    def processing_config(self) -> ProcessingConfig:
        return self._conf

    @cached_property
    def cache_manager(self) -> CacheManager:
        try:
            cm = CacheManager.get_service()
        except FactoryNotFoundError:
            CacheManager.initialize_handlers()
            cm = CacheManager(self._conf.projects)
            cm.register_as_service()
        return cm

    @cached_property
    def plugins(self) -> QgisPluginService:
        try:
            plugin_s = QgisPluginService.get_service()
        except FactoryNotFoundError:
            init_qgis_processing()
            # Load plugins
            plugin_s = QgisPluginService(self._conf.plugins)
            plugin_s.load_plugins(PluginType.PROCESSING, None)
            plugin_s.register_as_service()
        return plugin_s

    def project(self, path: str) -> QgsProject:
        from py_qgis_cache import CheckoutStatus as Co

        cm = self.cache_manager

        # Resolve location
        url = cm.resolve_path(path)
        # Check status
        md, status = cm.checkout(url)
        match status:
            case Co.REMOVED:
                raise FileNotFoundError(f"Project {url} was removed")
            case Co.NOTFOUND:
                raise FileNotFoundError(f"Project {url} does no exists")
            case _:
                entry, _ = cm.update(md, status)  # type: ignore [arg-type]
                project = entry.project
        return project
