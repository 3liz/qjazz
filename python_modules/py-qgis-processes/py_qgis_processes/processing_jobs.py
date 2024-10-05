#
# Processing jobs
#


from celery.signals import worker_process_init, worker_ready
from celery.worker.control import control_command, inspect_command
from typing_extensions import (
    Dict,
    Optional,
)

from py_qgis_contrib.core.celery import Job, JobContext

from .schemas import (
    JobExecute,
    JobResults,
)
from .worker.prelude import (
    QgisJob,
    QgisProcessJob,
    QgisWorker,
)
from .worker.processing import (
    FeedBack,
    ProcessingCache,
    QgisContext,
)

#
#  Signals
#

# Called at process initialization
# See https://docs.celeryq.dev/en/stable/userguide/signals.html#worker-process-init


@worker_process_init.connect
def init_qgis(*args, **kwargs):
    """ Initialize Qgis context in each process
    """
    QgisContext.setup_processing(app.processing_config)


@worker_ready.connect
def on_worker_ready(*args, **kwargs):
    app.processes_cache.update()


#
# Control commands
#

@control_command()
def reload_processes_cache(_):
    """ Reload the processes cache
    """
    app.processes_cache.update()


#
# Inspect commands
#
@inspect_command()
def list_processes(_) -> Dict:
    """Return processes list
    """
    return app.processes_cache.processes


@inspect_command(
    args=[('ident', str), ('project_path', str)],
)
def describe_process(_, ident: str, project_path: str | None) -> Dict | None:
    """Return process description
    """
    return app.processes_cache.describe(ident, project_path)


#
# Qgis Worker
#


class QgisProcessingWorker(QgisWorker):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.processes_cache = ProcessingCache(self.processing_config)
        self.processes_cache.start()

    def create_context(self) -> QgisContext:
        return QgisContext(self.processing_config)

    def on_worker_shutdown(self) -> None:
        self.processes_cache.stop()
        super().on_worker_shutdown()


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
    """Validate process inputs without executing
    """
    ctx.qgis_context.validate(
        ident,
        request,
        feedback=FeedBack(self.setprogress),
        project_path=project_path,
    )


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
        feedback=FeedBack(self.set_progress),
        project_path=project_path,
        public_url=public_url,
    )

    # Move files to store
    self.app.store_files(ctx.task_id, public_url)

    return result
