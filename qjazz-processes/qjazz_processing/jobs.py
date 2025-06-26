#
# Processing jobs
#

from typing import (
    Optional,
)

from celery.signals import worker_process_init

from qjazz_contrib.core.celery import Job, JobContext
from qjazz_processes.schemas import (
    JobExecute,
    JobResults,
)
from qjazz_processes.worker.prelude import (
    PROCESS_ENTRYPOINT,
    Feedback,
    ProcessCacheProtocol,
    QgisJob,
    QgisProcessJob,
    QgisWorker,
)

from .processing import (
    ProcessingCache,
    QgisProcessingContext,
)

#
#  Signals
#

# Called at process initialization
# See https://docs.celeryq.dev/en/stable/userguide/signals.html#worker-process-init


@worker_process_init.connect
def init_qgis(*args, **kwargs):
    """Initialize Qgis context in each process"""
    QgisProcessingContext.setup_processing(app.processing_config)


#
# Qgis Worker
#


class QgisProcessingWorker(QgisWorker):
    def create_context(self) -> QgisProcessingContext:
        return QgisProcessingContext(self.processing_config, service_name=self.service_name)

    def create_processes_cache(self) -> Optional[ProcessCacheProtocol]:
        processes_cache = ProcessingCache(self.processing_config)
        processes_cache.start()
        return processes_cache


app = QgisProcessingWorker()

#
# Processing tasks
#


@app.job(name="process_validate", base=QgisJob)
def validate_process_inputs(
    self: Job,
    ctx: JobContext,
    /,
    ident: str,
    request: JobExecute,
    project_path: Optional[str] = None,
):
    """Validate process inputs without executing"""
    ctx.qgis_context.validate(
        ident,
        request,
        feedback=Feedback(self.setprogress),
        project_path=project_path,
    )


@app.job(name=PROCESS_ENTRYPOINT, bind=True, run_context=True, base=QgisProcessJob)
def execute_process(
    self: Job,
    ctx: JobContext,
    /,
    ident: str,
    request: JobExecute,
    project_path: Optional[str] = None,
) -> JobResults:
    """Execute process"""
    # Optional context attributes
    public_url: str | None
    try:
        public_url = ctx.public_url
    except AttributeError:
        public_url = None

    result, _ = ctx.qgis_context.execute(
        ctx.task_id,
        ident,
        request,
        feedback=Feedback(self.set_progress),
        project_path=project_path,
        public_url=public_url,
    )

    # Move files to store
    self.app.store_files(ctx.task_id)

    return result
