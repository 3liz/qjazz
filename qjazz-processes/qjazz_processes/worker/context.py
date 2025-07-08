#
# Processing worker
#
import os

from contextlib import chdir, contextmanager  # noqa F401
from functools import cached_property
from pathlib import Path
from string import Template
from typing import (
    Callable,
    Iterator,
    Optional,
    Type,
)

from qgis.core import Qgis, QgsProcessingFeedback, QgsProject
from qgis.server import QgsServer

from qjazz_cache.extras import evict_by_popularity
from qjazz_cache.prelude import CacheManager
from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import assert_postcondition, assert_precondition
from qjazz_contrib.core.qgis import (
    init_qgis_application,
    init_qgis_server,
    qgis_initialized,
    show_qgis_settings,
)

from ..processing.config import ProcessingConfig
from ..processing.prelude import (
    JobExecute,
    JobResults,
    ProcessingContext,
)
from .exceptions import ProjectRequired


def store_reference_url(
    store_url: Template,
    job_id: str,
    resource: str,
    public_url: Optional[str],
) -> str:
    """Return a proper reference url for the resource"""
    return store_url.substitute(
        resource=resource,
        jobId=job_id,
        public_url=public_url or "",
    )


ProgressFun = Callable[[Optional[float], Optional[str]], None]


class Feedback(QgsProcessingFeedback):
    def __init__(self, progress_fun: ProgressFun):
        super().__init__(False)
        self._progress_msg = ""
        self._progress_fun = progress_fun

        # Connect slot
        self.progressChanged.connect(self._on_progress_changed)

    def __del__(self) -> None:
        try:
            self.progressChanged.disconnect(self._on_progress_changed)
        except Exception as err:
            logger.warning("%s", err)

    def _on_progress_changed(self, progress: float):
        self._progress_fun(progress, self._progress_msg)

    def pushFormattedMessage(_html: str, text: str):
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


Job = Callable[
    [JobExecute, QgsProcessingFeedback, ProcessingContext],
    JobResults,
]


class QgisContext:
    """Qgis context initializer"""

    PUBLISHED_FILES = ".files"
    EXPIRE_FILE = ".job-expire"

    @classmethod
    def setup(cls, conf: ProcessingConfig):
        """Initialize qgis"""

        debug = logger.is_enabled_for(logger.LogLevel.DEBUG)
        if debug:
            os.environ["QGIS_DEBUG"] = "1"

        #
        # Initialize Qgis application
        #
        init_qgis_application(settings=conf.settings())
        if debug:
            logger.debug(show_qgis_settings())

        #
        # Initialize network configuration
        #
        conf.network.configure_network()

        #
        # Initialize cache manager
        #
        logger.debug("Initializing cache manager...")

        CacheManager.initialize_handlers(conf.projects)
        cm = CacheManager(conf.projects)
        cm.register_as_service()

    @classmethod
    def published_files(cls, jobdir: Path) -> Iterator[Path]:
        published = jobdir.joinpath(QgisContext.PUBLISHED_FILES)
        if published.exists():
            with published.open() as f:
                files = (n for n in (name.strip() for name in f.readlines()) if n)
                for file in files:
                    p = jobdir.joinpath(file)
                    if not p.is_file():
                        continue
                    yield p

    def __init__(
        self,
        conf: ProcessingConfig,
        *,
        service_name: Optional[str] = None,
        with_expiration: bool = True,
    ):
        assert_precondition(qgis_initialized(), "Qgis context must be intialized")
        self._conf = conf
        self._with_expiration = with_expiration
        if service_name:
            self.EXPIRE_FILE = f"{self.EXPIRE_FILE}-{service_name}"

    def job_execute(
        self,
        job: Job,
        task_id: str,
        ident: str,
        request: JobExecute,
        *,
        require_project: bool = False,
        feedback: QgsProcessingFeedback,
        project_path: Optional[str] = None,
        public_url: Optional[str] = None,
    ) -> tuple[JobResults, Optional[QgsProject]]:
        """Execute process"""

        project = self.project(project_path) if project_path else None
        if not project and require_project:
            raise ProjectRequired(f"Algorithm {ident} require project")

        context = ProcessingContext(self.processing_config)
        context.setFeedback(feedback)
        context.job_id = task_id

        if public_url:
            context.public_url = public_url

        workdir = context.workdir
        workdir.mkdir(parents=True, exist_ok=not self._with_expiration)
        if self._with_expiration:
            # Create a sentinel .job-expire file
            workdir.joinpath(self.EXPIRE_FILE).open("a").close()

        if project:
            context.setProject(project)

        with execute_context(workdir, task_id):
            results = job(request, feedback, context)

        # Save list of published files
        with workdir.joinpath(self.PUBLISHED_FILES).open("w") as files:
            for file in context.files:
                print(file, file=files)  # noqa T201

        # Write modified project
        destination_project = context.destination_project
        if destination_project and destination_project.isDirty():
            self.publish_layers(destination_project)

            logger.debug("Writing destination project")
            assert_postcondition(
                destination_project.write(),
                f"Failed to save destination project {destination_project.fileName()}",
            )

        return results, destination_project

    @property
    def processing_config(self) -> ProcessingConfig:
        return self._conf

    def store_reference_url(self, job_id: str, resource: str, public_url: Optional[str]) -> str:
        return store_reference_url(self._conf.store_url, job_id, resource, public_url)

    @cached_property
    def cache_manager(self) -> CacheManager:
        return CacheManager.get_service()

    def project(self, path: str) -> QgsProject:
        from qjazz_cache.prelude import CheckoutStatus as Co

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

    def publish_layers(self, project: QgsProject):
        """Publish layers"""

        LayerType: Type = Qgis.LayerType

        def _layers_for(layertype: LayerType) -> Iterator[str]:  # type: ignore [valid-type]
            return (lid for lid, lyr in project.mapLayers().items() if lyr.type() == layertype)

        # Publishing vector layers in WFS and raster layers in WCS
        project.writeEntry("WFSLayers", "/", list(_layers_for(LayerType.Vector)))
        project.writeEntry("WCSLayers", "/", list(_layers_for(LayerType.Raster)))

        for lid in _layers_for(LayerType.Vector):
            project.writeEntry("WFSLayersPrecision", "/" + lid, 6)


#
#  Server context
#


class QgisServerContext(QgisContext):
    """Qgis server context initializer"""

    server: QgsServer

    @classmethod
    def setup(cls, conf: ProcessingConfig):
        debug = logger.is_enabled_for(logger.LogLevel.DEBUG)
        # Enable qgis server debug verbosity
        if debug:
            os.environ["QGIS_SERVER_LOG_LEVEL"] = "0"
            os.environ["QGIS_DEBUG"] = "1"

        projects = conf.projects
        if projects.trust_layer_metadata:
            os.environ["QGIS_SERVER_TRUST_LAYER_METADATA"] = "yes"
        if projects.disable_getprint:
            os.environ["QGIS_SERVER_DISABLE_GETPRINT"] = "yes"

        # Disable any cache strategy
        os.environ["QGIS_SERVER_PROJECT_CACHE_STRATEGY"] = "off"

        cls.server = init_qgis_server(settings=conf.qgis_settings)
        if debug:
            logger.debug(show_qgis_settings())

        CacheManager.initialize_handlers(conf.projects)
        cm = CacheManager(conf.projects)
        cm.register_as_service()


#
# Utils
#


@contextmanager
def execute_context(workdir: Path, task_id: str):
    with chdir(workdir), logger.logfile(workdir, "processing"), memlog(task_id):
        yield


@contextmanager
def memlog(task_id: str):
    import psutil

    process = psutil.Process(os.getpid())
    rss = process.memory_info().rss
    mb = 1024 * 1024.0
    try:
        yield
    finally:
        _leaked = (process.memory_info().rss - rss) / mb
        logger.info("Task %s leaked %.3f Mb", task_id, _leaked)
