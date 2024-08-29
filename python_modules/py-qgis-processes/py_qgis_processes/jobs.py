#
# Processing worker
#
import mimetypes
import shutil

from time import time

import redis

from celery.signals import (
    worker_process_init,
)
from celery.worker.control import inspect_command
from typing_extensions import (
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.condition import assert_precondition
from py_qgis_contrib.core.utils import to_utc_datetime

from . import registry
from .celery import Job, JobContext, Worker
from .config import load_configuration
from .context import FeedBack, QgisContext
from .exceptions import DismissedTaskError
from .models import (
    ProcessFilesVersion,
    ProcessLogVersion,
    WorkerPresenceVersion,
)
from .processing.prelude import (
    JobExecute,
    JobResults,
    ProcessDescription,
    ProcessSummary,
)
from .processing.schemas import Link

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

    def before_start(self, task_id, args, kwargs):
        # Add qgis context in job context
        self._worker_job_context.update(
            qgis_context=QgisContext(self._worker_job_context['processing_config']),
        )
        super().before_start(task_id, args, kwargs)


class QgisProcessJob(QgisJob):

    def before_start(self, task_id, args, kwargs):
        # Check if task is not dismissed while
        # being pending
        ti = registry.find_job(app, task_id)
        logger.debug("Processing task info %s", ti)
        if not ti or ti.dismissed:
            raise DismissedTaskError(task_id)
        super().before_start(task_id, args, kwargs)


class ProcessingWorker(Worker):

    def __init__(self, **kwargs) -> None:

        from kombu import Queue

        conf = load_configuration()

        service_name = conf.worker.service_name

        self.service_name = service_name

        super().__init__(service_name, conf.worker, **kwargs)

        # We want each service with its own queue and exchange
        # The queue used can be configured as running options
        # with '-Q <queue>' option.
        # This allows to use dedicated workers for inventory
        # and/or processes tasks (see also how to configure manual
        # routing for tasks).
        #
        # See https://docs.celeryq.dev/en/stable/userguide/routing.html
        # for task routing
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

        self._workdir = conf.processing.workdir
        self._store_url = conf.processing.store_url

        self._job_context.update(processing_config=conf.processing)

        self._service_name = service_name
        self._service_title = conf.worker.title
        self._service_description = conf.worker.description
        self._service_links = conf.worker.links
        self._online_since = time()

    def lock(self, name: str, timeout: int = 20) -> redis.lock.Lock:
        # Create a redis lock for handling race conditions
        # with multiple workers
        # See https://redis-py-doc.readthedocs.io/en/master/#redis.Redis.lock
        # The lock will hold only for 20s
        # so operation using the lock should not exceed this duration.
        return self.backend.client.lock(
            f"lock:{self.service_name}:{name}",
            blocking_timeout=0,
            timeout=timeout,
        )

    def store_reference_url(self, job_id: str, resource: str, public_url: Optional[str]) -> str:
        """ Return a proper reference url for the resource
        """
        return self._store_url.substitute(
            resource=resource,
            jobId=job_id,
            public_url=public_url or "",
        )


app = ProcessingWorker()

#
# Inspect commands
#


@inspect_command()
def presence(_) -> Dict:
    from qgis.core import Qgis, QgsCommandLineUtils
    return WorkerPresenceVersion(
        service=app._service_name,
        title=app._service_title,
        description=app._service_description,
        links=app._service_links,
        online_since=app._online_since,
        qgis_version_info=Qgis.versionInt(),
        versions=QgsCommandLineUtils.allVersions(),
        result_expires=app.conf.result_expires,
    ).model_dump()


@inspect_command(
    args=[('jobs', list[str])],
)
def cleanup(_, jobs: Sequence[str]):
    """Clean job data
    """
    try:
        with app.lock("cleanup"):
            workdir = app._workdir
            for job_id in jobs:
                jobdir = workdir.joinpath(job_id)
                try:
                    if not jobdir.exists():
                        continue
                    logger.info("%s: Removing response directory", job_id)
                    assert_precondition(jobdir.is_dir())
                    shutil.rmtree(jobdir)
                except Exception as err:
                    logger.error("Unable to remove directory '%s': %s", jobdir, err)
    except Exception as err:
        logger.warning("Cleanup: cannot acquire lock: %s", err)


@inspect_command(
    args=[('job_id', str)],
)
def process_logs(_, job_id: str) -> Dict:
    """Return job log
    """
    logfile = app._workdir.joinpath(job_id, "processing.log")
    if not logfile.exists():
        text = "No log available"
    else:
        with logfile.open() as f:
            text = f.read()

    return ProcessLogVersion(timestamp=to_utc_datetime(time()), log=text).model_dump()


@inspect_command(
    args=[('job_id', str, 'public_url', str)],
)
def process_files(_, job_id: str, public_url: str | None) -> Dict:
    """Returns job execution files"""

    workdir = app._workdir.joinpath(job_id)

    def _make_links(files: Iterator[str]) -> Iterator[Link]:
        for name in files:
            file = workdir.joinpath(name)
            if not file.is_file():
                continue

            content_type = mimetypes.types_map.get(file.suffix)
            size = file.stat().st_size
            yield Link(
                href=app.store_reference_url(job_id, name, public_url),
                mime_type=content_type,
                length=size,
                title=name,
            )

    files = workdir.joinpath(QgisContext.PUBLISHED_FILES)
    if files.exists():
        with files.open() as f:
            links = tuple(_make_links(name.strip() for name in f.readlines()))
    else:
        links = ()

    return ProcessFilesVersion(links=links).model_dump()

#
# Job tasks
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
