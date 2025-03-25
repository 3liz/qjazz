#
# Processing worker
#
import mimetypes
import shutil

from itertools import chain
from pathlib import Path
from time import time
from typing import (
    Callable,
    Iterable,
    Iterator,
    Optional,
    Sequence,
    cast,
)

import redis

from celery.signals import (
    worker_before_create_process,
    worker_ready,
    worker_shutdown,
)
from celery.worker.control import (
    control_command,
    inspect_command,
)
from pydantic import TypeAdapter

from qjazz_contrib.core import logger
from qjazz_contrib.core.celery import Job, Worker
from qjazz_contrib.core.condition import assert_precondition
from qjazz_contrib.core.utils import to_utc_datetime

from ..processing.config import ProcessingConfig
from . import registry
from .cache import ProcessCacheProto
from .config import load_configuration
from .context import QgisContext, store_reference_url
from .exceptions import DismissedTaskError
from .models import (
    Link,
    ProcessFilesVersion,
    ProcessLogVersion,
    WorkerPresenceVersion,
)
from .storage import Storage
from .threads import Event, PeriodicTask
from .watch import WatchFile

LinkSequence: TypeAdapter[Sequence[Link]] = TypeAdapter(Sequence[Link])


FILE_LINKS = "links.json"

#
#  Signals
#


@worker_ready.connect
def on_worker_ready(sender, *args, **kwargs):
    sender.app.on_worker_ready()


@worker_shutdown.connect
def on_worker_shutdown(sender, *args, **kwargs):
    sender.app.on_worker_shutdown()


@worker_before_create_process.connect
def on_worker_before_create_process(sender, *args, **kwargs):
    # XXX We don't have access to app from 'sender' object
    QgisWorker._storage.before_create_process()


#
# Control commands
#


@control_command()
def reload_processes_cache(_state):
    """Reload the processes cache"""
    app = cast(QgisWorker, _state.consumer.app)
    if app.processes_cache:
        app.processes_cache.update()


@inspect_command()
def list_processes(_state) -> dict:
    """Return processes list"""
    app = cast(QgisWorker, _state.consumer.app)
    if app.processes_cache:
        return app.processes_cache.processes
    else:
        return {}


@inspect_command(
    args=[("ident", str), ("project_path", str)],
)
def describe_process(_state, ident: str, project_path: str | None) -> dict | None:
    """Return process description"""
    app = cast(QgisWorker, _state.consumer.app)
    if app.processes_cache:
        return app.processes_cache.describe(ident, project_path)
    else:
        return None


@inspect_command()
def presence(_state) -> dict:
    """Returns informations about the service"""
    app = cast(QgisWorker, _state.consumer.app)

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
    """Run cleanup task"""
    app = cast(QgisWorker, state.consumer.app)
    app.cleanup_expired_jobs()


@inspect_command(
    args=[("job_id", str)],
)
def job_log(state, job_id):
    """Return job log"""
    app = cast(QgisWorker, state.consumer.app)
    return app.job_log(job_id).model_dump()


@inspect_command(
    args=[("job_id", str), ("public_url", str)],
)
def job_files(state, job_id, public_url):
    """Returns job execution files"""
    app = cast(QgisWorker, state.consumer.app)
    return app.job_files(job_id, public_url).model_dump()


@inspect_command(
    args=[("job_id", str), ("resource", str), ("expiration", int)],
)
def download_url(state, job_id, resource, expiration):
    try:
        app = cast(QgisWorker, state.consumer.app)
        return app.download_url(
            job_id,
            resource,
            expiration,
        ).model_dump()
    except FileNotFoundError as err:
        logger.error(err)
        return None


#
# Worker
#


class QgisWorker(Worker):
    _storage: Storage

    def __init__(self, **kwargs) -> None:
        conf = load_configuration()
        if logger.is_enabled_for(logger.LogLevel.DEBUG):
            logger.debug("== Worker configuration ==\n%s", conf.model_dump_json(indent=4))

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
        routing_name = f"qjazz.{service_name}"

        self.conf.task_default_queue = routing_name
        self.conf.task_default_exchange = routing_name

        # Allow worker to restart pool
        self.conf.worker_pool_restarts = True

        self._workdir = conf.processing.workdir
        self._store_url = conf.processing.store_url
        self._processing_config = conf.processing

        assert_precondition(not hasattr(QgisWorker, "_storage"))
        QgisWorker._storage = conf.storage.create_instance()

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
        self._periodic_tasks: list[PeriodicTask] = []

        self._service_name = service_name
        self._service_title = conf.worker.title
        self._service_description = conf.worker.description
        self._service_links = conf.worker.links
        self._online_since = time()

        self.processes_cache = self.create_processes_cache()

        self.add_periodic_task("cleanup", self.cleanup_expired_jobs, self._cleanup_interval)

        if conf.worker.reload_monitor:
            watch = WatchFile(conf.worker.reload_monitor, self.reload_processes)
            self.add_periodic_task("reload", watch, 5.0)

    def add_periodic_task(self, name: str, target: Callable[[], None], timeout: float):
        self._periodic_tasks.append(
            PeriodicTask(name, target, timeout, event=self._shutdown_event),
        )

    @property
    def processing_config(self) -> ProcessingConfig:
        return self._processing_config

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
        """Return a proper reference url for the resource"""
        return store_reference_url(
            self._store_url,
            job_id,
            resource,
            public_url,
        )

    def cleanup_expired_jobs(self) -> None:
        """Cleanup all expired jobs"""
        try:
            with self.lock("cleanup-batch"):
                logger.debug("Running cleanup task")
                # Search for expirable jobs resources
                for p in self._workdir.glob(f"*/.job-expire-{self.service_name}"):
                    jobdir = p.parent
                    job_id = jobdir.name
                    if registry.exists(self, job_id):
                        continue

                    logger.info("=== Cleaning jobs resource: %s", job_id)
                    self._storage.remove(job_id, workdir=self._workdir)

                    try:
                        shutil.rmtree(jobdir)
                    except Exception as err:
                        logger.error("Failed to remove directory '%s': %s", jobdir, err)

        except redis.lock.LockError:
            pass

    def reload_processes(self) -> None:
        """Reload processes"""
        if self.processes_cache:
            self.processes_cache.update()

        self.control.pool_restart(destination=(self.worker_hostname,))

    def on_worker_ready(self) -> None:
        # Launch periodic cleanup task
        for task in self._periodic_tasks:
            task.start()
        # Start process cache
        if self.processes_cache:
            self.processes_cache.update()

    def on_worker_shutdown(self) -> None:
        # Stop proccess cache
        if self.processes_cache:
            self.processes_cache.stop()
        # Stop cleanup scheduler
        self._worker_handle = None
        self._shutdown_event.set()
        for task in self._periodic_tasks:
            task.join(timeout=5.0)

    def job_log(self, job_id: str) -> ProcessLogVersion:
        """Return job log"""
        logfile = self._workdir.joinpath(job_id, "processing.log")
        if not logfile.exists():
            text = "No log available"
        else:
            with logfile.open() as f:
                text = f.read()

        return ProcessLogVersion(timestamp=to_utc_datetime(time()), log=text)

    def job_files(self, job_id: str, public_url: str | None) -> ProcessFilesVersion:
        """Returns job execution files"""
        p = self._workdir.joinpath(job_id, FILE_LINKS)
        if p.exists():
            with p.open() as f:
                links = LinkSequence.validate_json(f.read())

            # Update reference according to the given public_url
            def update_ref(link: Link) -> Link:
                href = self.store_reference_url(job_id, link.title, public_url)
                return link.model_copy(update={"href": href})

            files = ProcessFilesVersion(links=tuple(update_ref(link) for link in links))
        else:
            files = ProcessFilesVersion(links=())

        return files

    def download_url(self, job_id: str, resource: str, expiration: int) -> Link:
        """Returns a temporary download url"""
        return self._storage.download_url(
            job_id,
            resource,
            workdir=self._workdir,
            expires=expiration,
        )

    def store_files(self, job_id: str, add_auxiliary_files: bool = True):
        """Move files to storage

        If add_auxiliary_files is false then all attached files created
        by the jobs are ignored and only published files are transferred.
        """
        jobdir = self._workdir.joinpath(job_id)
        files = tuple(QgisContext.published_files(jobdir))

        # Write the downloadables file links
        def _make_links() -> Iterator[Link]:
            for p in files:
                # Drop non-relative files to current
                # workdir since we don't know how to
                # download them
                if not p.is_relative_to(jobdir):
                    continue

                name = str(p.relative_to(jobdir))
                content_type = mimetypes.types_map.get(p.suffix)
                size = p.stat().st_size
                yield Link(
                    href=self.store_reference_url(job_id, name, "$public_url"),
                    mime_type=content_type or "application/octet-stream",
                    length=size,
                    title=name,
                )

        with jobdir.joinpath(FILE_LINKS).open("w") as f:
            f.write(LinkSequence.dump_json(tuple(_make_links())).decode())

        files_to_store: Iterable[Path]
        if add_auxiliary_files:
            files_to_store = chain(
                files,
                jobdir.glob("**/*.zip"),
                jobdir.glob("**/*.qgs"),
                jobdir.glob("**/*.qgz"),
                jobdir.glob("**/*.qml"),
                jobdir.glob("**/*.sld"),
                jobdir.glob("**/*.db"),
            )
        else:
            files_to_store = files

        #
        # Import published files and auxiliary files
        #
        self._storage.move_files(
            job_id,
            workdir=self._workdir,
            files=files_to_store,
        )

    def create_context(self) -> QgisContext:
        return QgisContext(self.processing_config, service_name=self.service_name)

    def create_processes_cache(self) -> Optional[ProcessCacheProto]:
        return None


#
# Qgis jobs
#


class QgisJob(Job):
    def before_start(self, task_id, args, kwargs):
        # Add qgis context in job context
        self._worker_job_context.update(qgis_context=self.app.create_context())
        super().before_start(task_id, args, kwargs)


class QgisProcessJob(QgisJob):
    def before_start(self, task_id, args, kwargs):
        # Check if task is not dismissed while
        # being pending
        ti = registry.find_job(self.app, task_id)
        logger.debug("Job task info %s", ti)
        if not ti or ti.dismissed:
            raise DismissedTaskError(task_id)
        super().before_start(task_id, args, kwargs)
