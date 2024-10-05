#
# Processing worker
#

from functools import cached_property

from typing_extensions import (
    Callable,
    Iterator,
    List,
    Optional,
    Tuple,
    Type,
    cast,
)

from qgis.core import Qgis, QgsProcessingFeedback, QgsProject

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.condition import assert_postcondition
from py_qgis_contrib.core.qgis import (
    PluginType,
    QgisPluginService,
    init_qgis_processing,
)

from ..processing.config import ProcessingConfig
from ..processing.prelude import (
    JobExecute,
    JobResults,
    ProcessAlgorithm,
    ProcessDescription,
    ProcessingContext,
    ProcessSummary,
)
from .cache import ProcessCache
from .context import QgisContext as QgisContextBase
from .context import execute_context
from .exceptions import (
    ProcessNotFound,
    ProjectRequired,
)

ProgressFun = Callable[[Optional[float], Optional[str]], None]


class FeedBack(QgsProcessingFeedback):

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


class QgisContext(QgisContextBase):
    """Qgis context initializer
    """

    @classmethod
    def setup_processing(cls, conf: ProcessingConfig):
        """ Initialize qgis """

        cls.setup(conf)

        #
        # Init Qgis processing and plugins
        #
        logger.info("Initializing qgis processing...")
        init_qgis_processing()
        plugin_s = QgisPluginService(conf.plugins)
        plugin_s.load_plugins(PluginType.PROCESSING, None)
        plugin_s.register_as_service()

    def __init__(self, conf: ProcessingConfig, with_expiration: bool = True):
        super().__init__(conf)
        self._with_expiration = with_expiration

    @property
    def processing_config(self) -> ProcessingConfig:
        return cast(ProcessingConfig, self._conf)

    @cached_property
    def plugins(self) -> QgisPluginService:
        return QgisPluginService.get_service()

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
            raise ProcessNotFound(f"Algorithm '{ident}' not found")

        project = self.project(project_path) if project_path else None
        if not project and alg.require_project:
            raise ProjectRequired(f"Algorithm {ident} require project")

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
    ) -> Tuple[JobResults, Optional[QgsProject]]:
        """ Execute process """
        alg = ProcessAlgorithm.find_algorithm(ident)
        if alg is None:
            raise ProcessNotFound(f"Algorithm '{ident}' not found")

        project = self.project(project_path) if project_path else None
        if not project and alg.require_project:
            # FIXME return appropriate exception
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
            workdir.joinpath(self.EXPIRE_FILE).open('a').close()

        if project:
            context.setProject(project)

        with execute_context(workdir, task_id):
            results = alg.execute(request, feedback, context)

        # Save list of published files
        with workdir.joinpath(self.PUBLISHED_FILES).open('w') as files:
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

    def publish_layers(self, project: QgsProject):
        """ Publish layers """

        LayerType: Type = Qgis.LayerType

        def _layers_for(layertype: LayerType) -> Iterator[str]:  # type: ignore [valid-type]
            return (lid for lid, lyr in project.mapLayers().items() if lyr.type() == layertype)

        # Publishing vector layers in WFS and raster layers in WCS
        project.writeEntry("WFSLayers", "/", list(_layers_for(LayerType.Vector)))
        project.writeEntry("WCSLayers", "/", list(_layers_for(LayerType.Raster)))

        for lid in _layers_for(LayerType.Vector):
            project.writeEntry("WFSLayersPrecision", "/" + lid, 6)


#
#  Processes cache
#

class ProcessingCache(ProcessCache):

    def initialize(self):
        self.processing_config.projects._dont_resolve_layers = True
        QgisContext.setup_processing(self.processing_config)

    @cached_property
    def context(self) -> QgisContext:
        return QgisContext(self.processing_config)

    def _describe(self, ident: str, project: Optional[str]) -> ProcessDescription:
        description = self.context.describe(ident, project)
        if not description:
            raise ValueError(f"No description found for algorithm {ident}")
        return description

    def _update(self) -> List[ProcessSummary]:
        return self.context.processes
