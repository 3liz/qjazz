#
# Processing worker
#

from time import time

from celery.signals import worker_process_init
from celery.worker.control import inspect_command
from pydantic import TypeAdapter
from typing_extensions import (
    Dict,
    List,
    Optional,
    Sequence,
)

from .celery import Job, JobContext, Worker
from .config import load_configuration
from .context import FeedBack, QgisContext
from .processing.prelude import (
    JobExecute,
    JobResults,
    ProcessDescription,
    ProcessSummary,
)
from .processing.schemas import LinkHttp

#
# Create worker application
#

# Called at process initialization
# See https://docs.celeryq.dev/en/stable/userguide/signals.html#worker-process-init
@worker_process_init.connect
def init_qgis(*args, **kwargs):
    """ Initialize Qgis context in each process
    """
    from py_qgis_contrib.core import config
    conf = config.confservice.conf

    QgisContext.setup(conf.processing)


class QgisJob(Job):

    def before_start(self, *args, **kwargs):
        # Add qgis context in job context
        self._worker_job_context.update(
            qgis_context=QgisContext(self._worker_job_context['processing_config']),
        )
        super().before_start(*args, **kwargs)


class ProcessingWorker(Worker):

    def __init__(self, **kwargs) -> None:

        from kombu import Queue

        conf = load_configuration()

        service_name = conf.worker.service_name

        self.service_name = service_name

        super().__init__(service_name, conf.worker, **kwargs)

        self._job_class = QgisJob

        # We want each service with its own queue and exchange
        self.conf.task_default_queue = f"py-qgis.{service_name}"
        self.conf.task_default_exchange = f"py-qgis.{service_name}"

        self.conf.task_default_exchange_type = 'topic'
        self.conf.task_default_routing_key = 'task.default'
        self.conf.task_queues = {
            Queue(f"py-qgis.{service_name}.Tasks", routing_key='task.#'),
            Queue(f"py-qgis.{service_name}.Inventory", routing_key='processes.#'),
        }

        # See https://docs.celeryq.dev/en/stable/userguide/configuration.html#std-setting-worker_prefetch_multiplier
        self.conf.worker_prefetch_multiplier = 1

        # Logging
        self.conf.worker_redirect_stdouts = False
        self.conf.worker_hijack_root_logger = False

        self._job_context.update(processing_config=conf.processing)

        self._service_name = service_name
        self._service_title = conf.worker.title
        self._service_description = conf.worker.description
        self._service_links = conf.worker.links
        self._online_since = time()


app = ProcessingWorker()


# Inspect commands

LinkSequence: TypeAdapter = TypeAdapter(Sequence[LinkHttp])


@inspect_command()
def presence(_) -> Dict:
    from qgis.core import Qgis, QgsCommandLineUtils
    return {
        'service': app._service_name,
        'title': app._service_title,
        'description': app._service_description,
        'links': LinkSequence.dump_python(
            app._service_links,
            mode='json',
            by_alias=True,
            exclude_none=True,
        ),
        'online_since': app._online_since,
        'qgis_version_info': Qgis.versionInt(),
        'versions': QgsCommandLineUtils.allVersions(),
    }


#
# Jobs
#


@app.job(name="process_list", run_context=True)
def list_processes(ctx: JobContext, /) -> List[ProcessSummary]:
    """Return the list of processes
    """
    return ctx.qgis_context.processes


@app.job(name="process_describe", run_context=True)
def describe_process(
    ctx: JobContext,
    /,
    ident: str,
    project_path: Optional[str],
) -> ProcessDescription | None:
    """Return process description
    """
    return ctx.qgis_context.describe(ident, project_path)


@app.job(name="process_validate")
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


@app.job(name="process_execute", bind=True, run_context=True)
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
        feedback=FeedBack(self.setprogress),
        project_path=project_path,
        public_url=public_url,
    )
