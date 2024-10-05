
from celery.signals import worker_process_init
from celery.worker.control import inspect_command
from typing_extensions import (
    Dict,
    Optional,
)

from py_qgis_contrib.core.celery import Job, JobContext
from py_qgis_processes.schemas import (
    JobExecute,
    JobResults,
)
from py_qgis_processes.worker.context import (
    QgisServerContext,
)
from py_qgis_processes.worker.prelude import (
    QgisContext,
    QgisProcessJob,
    QgisWorker,
)


@worker_process_init.connect
def init_qgis(*args, **kwargs):
    """ Initialize Qgis context in each process
    """
    QgisServerContext.setup(app.processing_config)


# Inspect commands
#
@inspect_command()
def list_processes(_) -> Dict:
    """Return processes list
    """
    # TODO
    return {}


@inspect_command(
    args=[('ident', str), ('project_path', str)],
)
def describe_process(_, ident: str, project_path: str | None) -> Dict | None:
    """Return process description
    """
    # TODO
    return None

#
# Qgis Worker
#


class QgisPrinterWorker(QgisWorker):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def create_context(self) -> QgisContext:
        return QgisServerContext(self.processing_config)


app = QgisPrinterWorker()


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
    """
    public_url: str | None
    try:
        public_url = ctx.public_url
    except AttributeError:
        public_url = None
    """
    # TODO
    # ctx.qgis_context
    return {}
