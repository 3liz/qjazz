#
# Processing worker
#
import os

from functools import cached_property

from typing_extensions import (
    Callable,
    List,
    Optional,
)

from qgis.core import QgsProcessingFeedback, QgsProject

from py_qgis_cache import CacheManager
from py_qgis_cache.extras import evict_by_popularity
from py_qgis_contrib.core import logger
from py_qgis_contrib.core.condition import assert_postcondition, assert_precondition
from py_qgis_contrib.core.qgis import (
    PluginType,
    QgisPluginService,
    init_qgis_application,
    init_qgis_processing,
    qgis_initialized,
    show_qgis_settings,
)

from .processing.config import ProcessingConfig
from .processing.prelude import (
    JobExecute,
    JobResults,
    ProcessAlgorithm,
    ProcessDescription,
    ProcessingContext,
    ProcessSummary,
)

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
    @classmethod
    def setup(cls, conf: ProcessingConfig):
        """ Initialize qgis """

        debug = logger.isEnabledFor(logger.LogLevel.DEBUG)
        if debug:
            os.environ['QGIS_DEBUG'] = '1'

        #
        # Initialize Qgis application
        #
        init_qgis_application(settings=conf.settings())
        if debug:
            logger.debug(show_qgis_settings())  # noqa T201

        #
        # Init Qgis processing and plugins
        #
        logger.info("Initializing qgis processing...")
        init_qgis_processing()
        plugin_s = QgisPluginService(conf.plugins)
        plugin_s.load_plugins(PluginType.PROCESSING, None)
        plugin_s.register_as_service()

        #
        # Initialize cache manager
        #
        logger.info("Initializing cache manager...")
        CacheManager.initialize_handlers()
        cm = CacheManager(conf.projects)
        cm.register_as_service()

    def __init__(self, conf: ProcessingConfig):
        assert_precondition(qgis_initialized(), "Qgis context must be intialized")
        self._conf = conf

    @property
    def processing_config(self) -> ProcessingConfig:
        return self._conf

    @cached_property
    def cache_manager(self) -> CacheManager:
        return CacheManager.get_service()

    @cached_property
    def plugins(self) -> QgisPluginService:
        return QgisPluginService.get_service()

    def project(self, path: str) -> QgsProject:
        from py_qgis_cache import CheckoutStatus as Co

        cm = self.cache_manager

        # Resolve location
        url = cm.resolve_path(path)
        # Check status
        md, status = cm.checkout(url)
        match status:
            case Co.REMOVED:
                cm.update(md, status)  # type: ignore [arg-type]
                raise FileNotFoundError(f"Project {url} was removed")
            case Co.NOTFOUND:
                raise FileNotFoundError(f"Project {url} does no exists")
            case _:
                if status == Co.NEW and len(cm) >= self._conf.max_cached_projects:
                    # Evict project from cache
                    evicted = evict_by_popularity(cm)
                    if evicted:
                        logger.debug("Evicted project from cache: %s", evicted.uri)
                entry, _ = cm.update(md, status)  # type: ignore [arg-type]
                entry.hit_me()
                project = entry.project
        return project

    @property
    def processes(self) -> List[ProcessSummary]:
        """ List proceses """
        include_deprecated = self.processing_config.expose_deprecated_algorithms
        algs = ProcessAlgorithm.algorithms(include_deprecated=include_deprecated)
        return [alg.summary() for alg in algs]

    def describe(self, ident: str, project_path: Optional[str]) -> ProcessDescription | None:
        """ Describe process """
        alg = ProcessAlgorithm.find_algorithm(ident)
        if alg:
            project = self.project(project_path) if project_path else None
            return alg.description(project)
        else:
            return None

    def validate(
        self,
        ident: str,
        request: JobExecute,
        *,
        feedback: QgsProcessingFeedback,
        project_path: Optional[str] = None,
    ):
        """ validate process parameters """
        alg = ProcessAlgorithm.find_algorithm(ident)
        if alg is None:
            raise ValueError(f"Algorithm '{ident}' not found")

        project = self.project(project_path) if project_path else None
        if not project and alg.require_project:
            raise ValueError(f"Algorithm {ident} require project")

        context = ProcessingContext(self.processing_config)
        context.setFeedback(feedback)

        if project:
            context.setProject(project)

        alg.validate_execute_parameters(request, feedback, context)

    def execute(
        self,
        task_id: str,
        ident: str,
        request: JobExecute,
        *,
        feedback: QgsProcessingFeedback,
        project_path: Optional[str] = None,
        public_url: Optional[str] = None,
    ) -> JobResults:
        """ Execute process """
        alg = ProcessAlgorithm.find_algorithm(ident)
        if alg is None:
            raise ValueError(f"Algorithm '{ident}' not found")

        project = self.project(project_path) if project_path else None
        if not project and alg.require_project:
            raise ValueError(f"Algorithm {ident} require project")

        context = ProcessingContext(self.processing_config)
        context.setFeedback(feedback)
        context.job_id = task_id

        if public_url:
            context.public_url = public_url

        context.workdir.mkdir(parents=True, exist_ok=True)

        if project:
            context.setProject(project)

        results = alg.execute(request, feedback, context)

        # Write modified project
        destination_project = context.destination_project
        if destination_project and destination_project.isDirty():
            logger.debug("Writing destination project")
            assert_postcondition(
                destination_project.write(),
                f"Failed to save destination project {destination_project.fileName()}",
            )

        return results
