
from celery.signals import worker_process_init
from typing_extensions import (
    Optional,
)

from qjazz_contrib.core.celery import Job, JobContext
from qjazz_processes.schemas import (
    JobExecute,
    JobResults,
)
from qjazz_processes.worker.prelude import (
    Feedback,
    ProcessCacheProto,
    QgisContext,
    QgisProcessJob,
    QgisWorker,
)

from .context import (
    PrintServerCache,
    QgisPrintServerContext,
)


@worker_process_init.connect
def init_qgis(*args, **kwargs):
    """ Initialize Qgis context in each process
    """
    QgisPrintServerContext.setup(app.processing_config)


#
# Qgis Worker
#

class QgisPrintServerWorker(QgisWorker):

    def create_context(self) -> QgisContext:
        return QgisPrintServerContext(self.processing_config, service_name=self.service_name)

    def create_processes_cache(self) -> Optional[ProcessCacheProto]:
        processes_cache = PrintServerCache(self.processing_config)
        processes_cache.start()
        return processes_cache


app = QgisPrintServerWorker()


@app.job(name="process_execute", bind=True, run_context=True, base=QgisProcessJob)
def execute_process(
    self: Job,
    ctx: JobContext,
    /,
    ident: str,
    request: JobExecute,
    project_path: Optional[str] = None,
) -> JobResults:
    """Execute process
    """
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
        features=Feedback(self.set_progress),
        project_path=project_path,
        public_url=public_url,
    )

    self.app.store_files(ctx.task_id)

    return result
