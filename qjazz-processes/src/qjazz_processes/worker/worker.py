#
# Processing worker
#
import functools
import mimetypes

from itertools import chain
from pathlib import Path
from time import time
from typing import (
    Any,
    Callable,
    Iterable,
    Iterator,
    Optional,
    Protocol,
    Sequence,
    cast,
)

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
from qjazz_core import logger
from qjazz_core.celery import Job, Worker
from qjazz_core.condition import assert_precondition

from ..processing.config import ProcessingConfig
from . import registry
from .cache import ProcessCacheProtocol
from .config import (
    CONFIG_ENV_PATH,  # noqa F401
    confservice,
    load_configuration,
)
from .config import (
    ConfigProto as BaseConfigProto,
)
from .context import QgisContext, store_reference_url
from .exceptions import DismissedTaskError
from .mixins.callbacks import Callbacks, CallbacksMixin
from .mixins.joblog import JoblogMixin
from .mixins.storage import StorageMixin
from .models import (
    Link,
    ProcessFilesVersion,
    WorkerPresenceVersion,
)
from .storage import Storage
from .threads import PeriodicTasks
from .watch import WatchFile

LinkSequence: TypeAdapter[Sequence[Link]] = TypeAdapter(Sequence[Link])


PROCESS_ENTRYPOINT = "process_execute"

#
# Config
#


# Allow type validation
class ConfigProto(BaseConfigProto, Protocol):
    processing: ProcessingConfig


confservice.add_section("processing", ProcessingConfig, field=...)


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
def list_processes(_state) -> list:
    """Return processes list"""
    app = cast(QgisWorker, _state.consumer.app)
    if app.processes_cache:
        return app.processes_cache.processes
    else:
        return []


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


@functools.cache
def qgis_version_details() -> Sequence[str]:
    from qgis.core import QgsCommandLineUtils

    return tuple(
        filter(
            None,
            (line.strip() for line in QgsCommandLineUtils.allVersions().split("\n")),
        ),
    )


@inspect_command()
def presence(_state) -> dict:
    """Returns informations about the service"""
    app = cast(QgisWorker, _state.consumer.app)

    from qgis.core import Qgis

    return WorkerPresenceVersion(
        service=app._service_name,
        title=app._service_title,
        description=app._service_description,
        links=app._service_links,
        online_since=app._online_since,
        qgis_version_info=Qgis.versionInt(),
        versions=qgis_version_details() if not app._hide_presence_versions else [],
        result_expires=app.conf.result_expires,
        callbacks=list(app.processes_callbacks.schemes),
        entrypoint=PROCESS_ENTRYPOINT,
    ).model_dump()


@inspect_command(
    args=[("job_id", str), ("public_url", str)],
)
def job_files(state, job_id, public_url):
    """Returns job execution files"""
    app = cast(QgisWorker, state.consumer.app)
    return app.job_files(job_id, public_url).model_dump()


#
# Worker
#


class QgisWorker(Worker, CallbacksMixin, StorageMixin, JoblogMixin):
    _storage: Storage

    @staticmethod
    def load_configuration() -> ConfigProto:
        return cast(ConfigProto, load_configuration())

    def __init__(self, **kwargs) -> None:
        conf = QgisWorker.load_configuration()
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

        # Hide presence versions
        self._hide_presence_versions = conf.worker.hide_presence_versions

        assert_precondition(not hasattr(QgisWorker, "_storage"))
        QgisWorker._storage = conf.storage.create_instance()

        self._processes_callbacks = Callbacks(conf.callbacks)
        self._periodic_tasks = PeriodicTasks()

        self._service_name = service_name
        self._service_title = conf.worker.title
        self._service_description = conf.worker.description
        self._service_links = conf.worker.links
        self._online_since = time()

        self.add_periodic_task("cleanup", self.cleanup_expired_jobs, conf.worker.cleanup_interval)

        self._workdir = conf.processing.workdir
        self._store_url = conf.processing.store_url
        self._processing_config = conf.processing

        self._reload_monitor = conf.worker.reload_monitor
        self.processes_cache = None

    def start_worker(self, **kwargs):
        self.processes_cache = self.create_processes_cache()

        if self._reload_monitor:
            watch = WatchFile(self._reload_monitor, self.reload_processes)
            self.add_periodic_task("reload", watch, 5.0)

        super().start_worker(**kwargs)

    def add_periodic_task(self, name: str, target: Callable[[], None], timeout: float):
        self._periodic_tasks.add(name, target, timeout)

    @property
    def processing_config(self) -> ProcessingConfig:
        return self._processing_config

    @property
    def service_name(self) -> str:
        return self._service_name

    def store_reference_url(self, job_id: str, resource: str, public_url: Optional[str]) -> str:
        """Return a proper reference url for the resource"""
        return store_reference_url(
            self._store_url,
            job_id,
            resource,
            public_url,
        )

    def reload_processes(self) -> None:
        """Reload processes"""
        if self.processes_cache:
            self.processes_cache.update()

        self.control.pool_restart(destination=(self.worker_hostname,))

    def on_worker_ready(self) -> None:
        self._periodic_tasks.start()
        # Start process cache
        if self.processes_cache:
            self.processes_cache.update()

    def on_worker_shutdown(self) -> None:
        # Stop proccess cache
        if self.processes_cache:
            self.processes_cache.stop()
        self._periodic_tasks.shutdown()

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

    def create_processes_cache(self) -> Optional[ProcessCacheProtocol]:
        return None

    @property
    def processes_callbacks(self) -> Callbacks:
        return self._processes_callbacks


#
# Qgis jobs
#


class QgisJob(Job):
    def update_run_context(self, task_id: str, context: dict[str, Any]):
        # Add qgis context in job context
        context.update(qgis_context=self.app.create_context())


class QgisProcessJob(QgisJob):
    def before_start(self, task_id, args, kwargs):
        # Check if task is not dismissed while
        # being pending
        ti = registry.find_job(self.app, task_id)
        logger.debug("Job task info %s", ti)
        if not ti or ti.dismissed:
            raise DismissedTaskError(task_id)
        super().before_start(task_id, args, kwargs)
