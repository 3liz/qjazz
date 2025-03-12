
from functools import cached_property
from typing import Optional

from qgis.core import QgsProcessingFeedback, QgsProject

from qjazz_processes.processing.prelude import (
    JobExecute,
    JobResults,
    ProcessDescription,
    ProcessingContext,
    ProcessSummary,
)
from qjazz_processes.worker.cache import ProcessCache
from qjazz_processes.worker.context import QgisServerContext
from qjazz_processes.worker.prelude import ProcessNotFound

from .getprint import GetPrintProcess


class QgisPrintServerContext(QgisServerContext):

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

        match ident:
            case "getprint":
                callee = GetPrintProcess.execute
            case _:
                raise ProcessNotFound(f"Process '{ident}' not found")

        def job(
            request: JobExecute,
            feedback: QgsProcessingFeedback,
            context: ProcessingContext,
        ) -> JobResults:
            return callee(request, feedback, context, self.server)

        return super().job_execute(
            job,
            task_id,
            ident,
            request,
            require_project=True,
            feedback=feedback,
            project_path=project_path,
            public_url=public_url,
        )

    @property
    def processes(self) -> list[ProcessSummary]:
        """ List proceses """
        return [GetPrintProcess.summary()]

    def describe(self, ident: str, project_path: Optional[str]) -> ProcessDescription | None:
        """ Describe process """
        match ident:
            case "getprint":
                return GetPrintProcess.description(project_path)
            case _:
                return None


#
#  Processes cache
#

class PrintServerCache(ProcessCache):

    def initialize(self):
        self.processing_config.projects._dont_resolve_layers = True
        QgisPrintServerContext.setup(self.processing_config)

    @cached_property
    def context(self) -> QgisPrintServerContext:
        return QgisPrintServerContext(self.processing_config)

    def _describe(self, ident: str, project: Optional[str]) -> ProcessDescription:
        description = self.context.describe(ident, project)
        if not description:
            raise ValueError(f"No description found for algorithm {ident}")
        return description

    def _update(self) -> list[ProcessSummary]:
        return self.context.processes
