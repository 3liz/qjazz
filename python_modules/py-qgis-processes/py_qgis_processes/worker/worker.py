#
# Processing worker
#
import mimetypes
import shutil

from time import time

import redis

from celery.signals import (
    worker_ready,
    worker_shutdown,
)
from celery.worker.control import (
    control_command,
    inspect_command,
)
from typing_extensions import (
    Any,
    Callable,
    Iterator,
    List,
    Optional,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.celery import Job, Worker
from py_qgis_contrib.core.utils import to_utc_datetime

from .. import registry
from ..exceptions import DismissedTaskError
from ..models import (
    ProcessFilesVersion,
    ProcessLogVersion,
    WorkerPresenceVersion,
)
from ..processing.config import ProcessingConfig
from ..schemas import Link
from .config import load_configuration
from .context import QgisContext
from .threads import Event, PeriodicTask
from .watch import WatchFile

#
#  Signals
#


@worker_ready.connect
def on_worker_ready(sender, *args, **kwargs):
    sender.app.on_worker_ready()


@worker_shutdown.connect
def on_worker_shutdown(sender, *args, **kwargs):
    sender.app.on_worker_shutdown()


#
# Control commands
#


@inspect_command()
def presence(state):
    """Returns informations about the service
    """
    app = state.consumer.app

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


@control_command()
def cleanup(state):
    """Run cleanup task
    """
    state.consumer.app.cleanup_expired_jobs()


@inspect_command(
    args=[('job_id', str)],
)
def job_log(state, job_id):
    """Return job log
    """
    return state.consumer.app.job_log(job_id).model_dump()


@inspect_command(
    args=[('job_id', str), ('public_url', str)],
)
def job_files(state, job_id, public_url):
    """Returns job execution files
    """
    return state.consumer.app.job_files(job_id, public_url).model_dump()


#
# Worker
#


class QgisWorker(Worker):

    def __init__(self, **kwargs) -> None:

        conf = load_configuration()

        service_name = conf.worker.service_name

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

        # Allow worker to restart pool
        self.conf.worker_pool_restarts = True

        self._workdir = conf.processing.workdir
        self._store_url = conf.processing.store_url

        self._job_context.update(processing_config=conf.processing)

        #
        # Init cleanup task
        #
        def cleanup_task():
            logger.info("Cleanup task started")
            while not self._cleanup_event.wait(self._cleanup_interval):
                self.cleanup_expired_jobs()
            logger.info("Cleanup task stopped")

        self._cleanup_interval = conf.worker.cleanup_interval
        self._shutdown_event = Event()
        self._periodic_tasks: List[PeriodicTask] = []

        self._service_name = service_name
        self._service_title = conf.worker.title
        self._service_description = conf.worker.description
        self._service_links = conf.worker.links
        self._online_since = time()

        self.processes_cache: Any = None

        self.add_periodic_task("cleanup", self.cleanup_expired_jobs, self._cleanup_interval)

        if conf.worker.reload_monitor:
            watch = WatchFile(conf.worker.reload_monitor, self.reload_processes)
            self.add_periodic_task("reload", watch, 5.)

    def add_periodic_task(self, name: str, target: Callable[[], None], timeout: float):
        self._periodic_tasks.append(
            PeriodicTask(name, target, timeout, event=self._shutdown_event),
        )

    @property
    def processing_config(self) -> ProcessingConfig:
        return self._job_context['processing_config']

    @property
    def service_name(self) -> str:
        return self._service_name

    def lock(self, name: str) -> redis.lock.Lock:
        # Create a redis lock for handling race conditions
        # with multiple workers
        # See https://redis-py-doc.readthedocs.io/en/master/#redis.Redis.lock
        # The lock will hold only for 20s
        # so operation using the lock should not exceed this duration.
        return self.backend.client.lock(
            f"lock:{self._service_name}:{name}",
            blocking_timeout=0,  # Do not block
            timeout=60,  # Hold lock 1mn max
        )

    def store_reference_url(self, job_id: str, resource: str, public_url: Optional[str]) -> str:
        """ Return a proper reference url for the resource
        """
        return self._store_url.substitute(
            resource=resource,
            jobId=job_id,
            public_url=public_url or "",
        )

    def cleanup_expired_jobs(self) -> None:
        """ Cleanup all expired jobs
        """
        try:
            with self.lock("cleanup-batch"):
                logger.debug("Running cleanup task")
                # Search for expirable jobs resources
                for p in self._workdir.glob("*/.job-expire"):
                    jobdir = p.parent
                    job_id = jobdir.name
                    if registry.exists(self, job_id):
                        continue
                    try:
                        logger.info("=== Cleaning jobs resource: %s", job_id)
                        shutil.rmtree(jobdir)
                    except Exception as err:
                        logger.error("Failed to remove directory '%s': %s", jobdir, err)
        except redis.lock.LockError:
            pass

    def reload_processes(self) -> None:
        """ Reload processes """
        destinations = (self.worker_hostname,)
        # Send control command to ourself
        if self.processes_cache:
            self.control.broadcast(
                "reload_processes_cache",
                destination=destinations,
                reply=True,
            )
        self.control.pool_restart(destination=(self.worker_hostname,))

    def on_worker_ready(self) -> None:
        # Launch periodic cleanup task
        for task in self._periodic_tasks:
            task.start()

    def on_worker_shutdown(self) -> None:
        # Stop cleanup scheduler
        self._worker_handle = None
        self._shutdown_event.set()
        for task in self._periodic_tasks:
            task.join(timeout=5.0)

    def job_log(self, job_id: str) -> ProcessLogVersion:
        """Return job log
        """
        logfile = self._workdir.joinpath(job_id, "processing.log")
        if not logfile.exists():
            text = "No log available"
        else:
            with logfile.open() as f:
                text = f.read()

        return ProcessLogVersion(timestamp=to_utc_datetime(time()), log=text)

    def job_files(self, job_id: str, public_url: str | None) -> ProcessFilesVersion:
        """Returns job execution files"""

        workdir = self._workdir.joinpath(job_id)

        def _make_links(files: Iterator[str]) -> Iterator[Link]:
            for name in files:
                file = workdir.joinpath(name)
                if not file.is_file():
                    continue

                content_type = mimetypes.types_map.get(file.suffix)
                size = file.stat().st_size
                yield Link(
                    href=self.store_reference_url(job_id, name, public_url),
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

        return ProcessFilesVersion(links=links)


#
# Qgis jobs
#


class QgisJob(Job):

    def before_start(self, task_id, args, kwargs):
        # Add qgis context in job context
        self._worker_job_context.update(
            qgis_context=QgisContext(
                self._worker_job_context['processing_config'],
                with_expiration=True,
            ),
        )
        super().before_start(task_id, args, kwargs)


class QgisProcessJob(QgisJob):

    def before_start(self, task_id, args, kwargs):
        # Check if task is not dismissed while
        # being pending
        ti = registry.find_job(self.app, task_id)
        logger.debug("Processing task info %s", ti)
        if not ti or ti.dismissed:
            raise DismissedTaskError(task_id)
        super().before_start(task_id, args, kwargs)
