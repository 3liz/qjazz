#
# Processing worker
#

from functools import cached_property
from pathlib import Path
from string import Template
from typing import Optional

from qjazz_core import logger
from qjazz_core.qgis import (
    PluginType,
    QgisPluginService,
    init_qgis_processing,
)

from qgis.core import QgsProcessingFeedback, QgsProject

from qjazz_processes.processing.config import ProcessingConfig
from qjazz_processes.processing.prelude import (
    JobExecute,
    JobResults,
    ProcessAlgorithm,
    ProcessDescription,
    ProcessingContext,
    ProcessSummary,
)
from qjazz_processes.worker.cache import ProcessCache
from qjazz_processes.worker.context import QgisContext
from qjazz_processes.worker.exceptions import (
    ProcessNotFound,
    ProjectRequired,
)


class QgisProcessingContext(QgisContext):
    """Qgis context initializer"""

    @classmethod
    def setup_processing(cls, conf: ProcessingConfig):
        """Initialize qgis"""

        cls.setup(conf)

        #
        # Init Qgis processing and plugins
        #
        logger.debug("Initializing qgis processing...")
        init_qgis_processing()
        plugin_s = QgisPluginService(conf.plugins)
        plugin_s.load_plugins(PluginType.PROCESSING, None)
        plugin_s.register_as_service()

    @cached_property
    def plugins(self) -> QgisPluginService:
        return QgisPluginService.get_service()

    @property
    def processes(self) -> list[ProcessSummary]:
        """List proceses"""
        include_deprecated = self.processing_config.expose_deprecated_algorithms
        algs = ProcessAlgorithm.algorithms(
            include_deprecated=include_deprecated,
            exposed_providers=self.processing_config.exposed_providers,
        )
        return [alg.summary() for alg in algs]

    def describe(self, ident: str, project_path: Optional[str]) -> ProcessDescription | None:
        """Describe process"""
        alg = ProcessAlgorithm.find_algorithm(ident)
        if alg:
            project = self.project(project_path) if project_path else None
            return alg.description(project)
        return None

    def validate(
        self,
        ident: str,
        request: JobExecute,
        *,
        feedback: QgsProcessingFeedback,
        project_path: Optional[str] = None,
    ):
        """validate process parameters"""
        alg = ProcessAlgorithm.find_algorithm(ident)
        if alg is None:
            raise ProcessNotFound(f"Algorithm '{ident}' not found")

        project = self.project(project_path) if project_path else None
        if not project and alg.require_project:
            raise ProjectRequired(f"Algorithm {ident} require project")

        context = ProcessingContext(self.workdir, self.processing_config, store_url = self.store_url)
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
    ) -> tuple[JobResults, Optional[QgsProject]]:
        """Execute process"""
        alg = ProcessAlgorithm.find_algorithm(ident)
        if alg is None:
            raise ProcessNotFound(f"Algorithm '{ident}' not found")

        return super().job_execute(
            alg.execute,
            task_id,
            ident,
            request,
            require_project=alg.require_project,
            feedback=feedback,
            project_path=project_path,
            public_url=public_url,
        )


#
#  Processes cache
#


class ProcessingCache(ProcessCache):
    def initialize(self):
        self._processing_config.projects._dont_resolve_layers = True
        QgisProcessingContext.setup_processing(self._processing_config)

    def __init__(self, workdir: Path, store_url: Template, conf: ProcessingConfig):
        super().__init__()
        self._workdir = workdir
        self._store_url = store_url
        self._processing_config = conf

    @cached_property
    def context(self) -> QgisProcessingContext:
        return QgisProcessingContext(
            self._processing_config,
            workdir = self._workdir,
            store_url = self._store_url,
        )

    def _describe(self, ident: str, project: Optional[str]) -> ProcessDescription:
        description = self.context.describe(ident, project)
        if not description:
            raise ValueError(f"No description found for algorithm {ident}")
        return description

    def _update(self) -> list[ProcessSummary]:
        return self.context.processes
