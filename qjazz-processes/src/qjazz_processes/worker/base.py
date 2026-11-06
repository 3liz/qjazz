#
# Processing worker
#

from contextlib import contextmanager
from pathlib import Path
from string import Template
from time import time
from typing import (
    Callable,
    cast,
)

from celery.signals import (
    worker_ready,
    worker_shutdown,
)
from celery.worker.control import (
    inspect_command,
)
from qjazz_core import logger
from qjazz_core.celery import Job, Worker

from . import registry
from .config import (
    CONFIG_ENV_PATH,  # noqa F401
    ConfigProto,
)
from .exceptions import DismissedTaskError
from .mixins.callbacks import Callbacks, CallbacksMixin
from .mixins.joblog import JoblogMixin
from .mixins.storage import StorageMixin
from .threads import PeriodicTasks
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

@inspect_command(
    args=[("job_id", str), ("public_url", str)],
)
def job_files(state, job_id, public_url):
    """Returns job execution files"""
    app = cast("WorkerBase", state.consumer.app)
    return app.job_files(job_id, public_url).model_dump()


#
# Worker
#


class WorkerBase(Worker, CallbacksMixin, StorageMixin, JoblogMixin):

    def __init__(self, conf: ConfigProto, **kwargs) -> None:
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

        # Initializing storage configuration
        self.init_storage(
            self.workdir,
            self.store_url,
            conf.storage.create_instance(),
        )

        self._processes_callbacks = Callbacks(conf.callbacks)
        self._periodic_tasks = PeriodicTasks()

        self._service_name = service_name
        self._service_title = conf.worker.title
        self._service_description = conf.worker.description
        self._service_links = conf.worker.links
        self._online_since = time()

        self.add_periodic_task("cleanup", self.cleanup_expired_jobs, conf.worker.cleanup_interval)

        self._reload_monitor = conf.worker.reload_monitor

    @property
    def workdir(self) -> Path:
        raise NotImplementedError()

    @property
    def store_url(self) -> Template:
        raise NotImplementedError()

    def start_worker(self, **kwargs):
        if self._reload_monitor:
            watch = WatchFile(self._reload_monitor, self.reload_processes)
            self.add_periodic_task("reload", watch, 5.0)

        super().start_worker(**kwargs)

    def add_periodic_task(self, name: str, target: Callable[[], None], timeout: float):
        self._periodic_tasks.add(name, target, timeout)

    @property
    def service_name(self) -> str:
        return self._service_name

    def reload_processes(self) -> None:
        """Reload processes"""
        self.control.pool_restart(destination=(self.worker_hostname,))

    def on_worker_ready(self) -> None:
        self._periodic_tasks.start()

    def on_worker_shutdown(self) -> None:
        self._periodic_tasks.shutdown()

    @property
    def processes_callbacks(self) -> Callbacks:
        return self._processes_callbacks

#
# Job
#


class ProcessJob(Job):

    @contextmanager
    def prepare_request(self, task_id, args, kwargs):
        raise NotImplementedError()

    def before_start(self, task_id, args, kwargs):
        # Check if task is not dismissed while
        # being pending
        ti = registry.find_job(self.app, task_id)
        if not ti or ti.dismissed:
            raise DismissedTaskError(task_id)

        # The job may run up to the task time limit: keep the job registered
        # until its results expire.
        registry.set_expiration(
            self.app,
            task_id,
            (self.app.conf.task_time_limit or 0) + self.app.conf.result_expires,
        )

        with self.prepare_request(task_id, args, kwargs):
            super().before_start(task_id, args, kwargs)

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        # Job is done: keep the job registered as long as its results
        registry.set_expiration(self.app, task_id, self.app.conf.result_expires)
        super().after_return(status, retval, task_id, args, kwargs, einfo)
