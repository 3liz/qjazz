"""Generic worker

- Does not depend on QGIS
- Define processes from worker jobs
"""

from pathlib import Path
from time import time
from typing import (
    Optional,
    Sequence,
    cast,
)
from uuid import UUID

from celery.signals import (
    worker_before_create_process,
    worker_ready,
    worker_shutdown,
)
from celery.worker.control import (
    inspect_command,
)
from pydantic import TypeAdapter
from qjazz_core import logger
from qjazz_core.celery import Job, Worker
from qjazz_core.condition import assert_precondition

from ..schemas import (
    JsonValue,
    MetadataValue,
    ProcessSummary,
    ProcessSummaryList,
)
from . import registry
from .config import load_configuration
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
    GenericWorker._storage.before_create_process()


#
# Control commands
#


@inspect_command()
def list_processes(_state) -> list:
    """Return processes summary list"""
    return ProcessSummaryList.dump_python(
        [
            ProcessSummary(
                id=ident,
                title=p.title,
                metadata=[
                    MetadataValue(
                        role=md.role,
                        title=md.title,
                        value=md.value,
                    )
                    for md in p.metadata
                ],
                description=p.description,
            )
            for ident, p in Job.RUN_CONFIGS.items()
        ],
        mode="json",
        exclude_none=True,
    )


@inspect_command(
    args=[("ident", str), ("project_path", str)],
)
def describe_process(_state, ident: str, project_path: str | None) -> dict | None:
    """Return process description"""
    p = Job.RUN_CONFIGS.get(ident)
    if p:
        return p.model_dump(mode="json", exclude_none=True, by_alias=True)
    return None


@inspect_command()
def presence(_state) -> dict:
    """Returns informations about the service"""
    app = cast("GenericWorker", _state.consumer.app)
    return app.presence().model_dump()


@inspect_command(
    args=[("job_id", str), ("public_url", str)],
)
def job_files(state, job_id, public_url):
    """Returns job execution files"""
    app = cast("GenericWorker", state.consumer.app)
    return app.job_files(job_id, public_url).model_dump()


#
# Worker
#


class GenericWorker(Worker, CallbacksMixin, StorageMixin, JoblogMixin):
    _storage: Storage
    _class_id: Optional[UUID] = None

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

        # Hide presence versions
        self._hide_presence_versions = conf.worker.hide_presence_versions

        self._workdir = Path().absolute()

        assert_precondition(not hasattr(GenericWorker, "_storage"))
        GenericWorker._storage = conf.storage.create_instance()

        self._processes_callbacks = Callbacks(conf.callbacks)
        self._periodic_tasks = PeriodicTasks()

        self._service_name = service_name
        self._service_title = conf.worker.title
        self._service_description = conf.worker.description
        self._service_links = conf.worker.links
        self._online_since = time()

        self._periodic_tasks.add("cleanup", self.cleanup_expired_jobs, conf.worker.cleanup_interval)

    @property
    def service_name(self) -> str:
        return self._service_name

    def on_worker_ready(self) -> None:
        self._periodic_tasks.start()

    def on_worker_shutdown(self) -> None:
        self._periodic_tasks.shutdown()

    def job_files(self, job_id: str, public_url: str | None) -> ProcessFilesVersion:
        """Returns job execution files"""
        return ProcessFilesVersion(links=())

    @property
    def processes_callbacks(self) -> Callbacks:
        return self._processes_callbacks

    def presence(self) -> WorkerPresenceVersion:
        return WorkerPresenceVersion(
            service=self._service_name,
            title=self._service_title,
            description=self._service_description,
            links=self._service_links,
            online_since=self._online_since,
            versions=[],
            result_expires=self.conf.result_expires,
            callbacks=list(self.processes_callbacks.schemes),
            class_id=self._class_id,
        )


#
# Jobs
#


class GenericJob(Job):
    def __call__(self, *arg, **kwargs) -> JsonValue:
        # Output must be wrapped in a dictionnary in order
        # to conform to the run_config schema
        return {"output": super().__call__(*arg, **kwargs)}

    def before_start(self, task_id, args, kwargs):
        # Check if task is not dismissed while
        # being pending
        ti = registry.find_job(self.app, task_id)
        if not ti or ti.dismissed:
            raise DismissedTaskError(task_id)

        # We receive argument as job processes request
        # in order to match the task signature, replace
        # the __run_config__ with the request 'inputs'
        request = kwargs["__run_config__"]["request"]
        try:
            kwargs["__run_config__"] = request["inputs"]
            super().before_start(task_id, args, kwargs)
        finally:
            # Keep subscriber for postrun
            kwargs["request"] = {"subscriber": request["subscriber"]}
