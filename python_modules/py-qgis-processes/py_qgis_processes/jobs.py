#
# Processing jobs
#

from celery.signals import worker_process_init
from typing_extensions import (
    Dict,
    List,
    Optional,
)

from py_qgis_contrib.core.celery import Job, JobContext

from .context import FeedBack, QgisContext
from .schemas import (
    JobExecute,
    JobResults,
    ProcessDescription,
    ProcessSummary,
)
from .worker import (
    QgisJob, 
    QgisProcessJob,
    QgisWorker,
    app, 
    inspect_command,
)

#
#
#


def get_processes_list(app: QgisWorker) -> Dict:
    #
    def _get_process_list(q: mp.Queue) -> Dict:
        QgisContext.setup_processing(app.processing_config)
        ctx=QgisContext(app.processing_config)
        q.put(ctx.processes)

    q = mp.Queue()
    p = mp.Process(target=_get_processes, args=(q,))
    def _processes(app: QgisWorker)
    p = Process(target=_processes)
    p.start()

app.on_reload_callback = get_processes_list


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

#
# Inspect commands
#

INVENTORY_TIMEOUT=5.

@inspect_command()
def list_processes(_) -> Dict:
    """Return processes list
    """

@inspect_command(
    args=[('ident', str), ('project_path', str)],
)
def describe_process(_, ident: str, project_path: str | None) -> Dict:
    """Return process description
    """
  

#
# Processing tasks
#


@app.job(name="process_list", run_context=True, base=QgisJob)
def list_processes(ctx: JobContext, /) -> List[ProcessSummary]:
    """Return the list of processes
    """
    return ctx.qgis_context.processes


@app.job(name="process_describe", run_context=True, base=QgisJob)
def describe_process(
    ctx: JobContext,
    /,
    ident: str,
    project_path: Optional[str],
) -> ProcessDescription | None:
    """Return process description
    """
    return ctx.qgis_context.describe(ident, project_path)


@app.job(name="process_validate", base=QgisJob)
def validate_process_inputs(
    self: Job,
    ctx: JobContext,
    /,
    ident: str,
    request: JobExecute,
    project_path: Optional[str] = None,
):
    """Validate process inputs

       Validate process inputs without executing
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

    return ctx.qgis_context.execute(
        ctx.task_id,
        ident,
        request,
        feedback=FeedBack(self.set_progress),
        project_path=project_path,
        public_url=public_url,
    )
