#
# Processing worker
#
import functools

from contextlib import contextmanager
from pathlib import Path
from string import Template
from typing import (
    Any,
    Optional,
    Protocol,
    Sequence,
    cast,
)

from celery.signals import (
    worker_before_create_process,
)
from celery.worker.control import (
    control_command,
    inspect_command,
)
from qjazz_core.celery import Job

from ..processing.config import ProcessingConfig
from .base import ProcessJob, WorkerBase
from .cache import ProcessCacheProtocol
from .config import (
    CONFIG_ENV_PATH,  # noqa F401
    confservice,
    load_configuration,
)
from .config import (
    ConfigProto as BaseConfigProto,
)
from .context import QgisContext
from .mixins.callbacks import CallbacksMixin
from .mixins.joblog import JoblogMixin
from .mixins.storage import StorageMixin
from .models import (
    WorkerPresenceVersion,
)

PROCESS_ENTRYPOINT = "process_execute"

#
# Config
#


# Allow type validation
class ConfigProto(BaseConfigProto, Protocol):
    processing: ProcessingConfig


confservice.add_section("processing", ProcessingConfig, field=...)



#
#  Signals
#


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
    app = cast("QgisWorker", _state.consumer.app)
    if app.processes_cache:
        app.processes_cache.update()


@inspect_command()
def list_processes(_state) -> list:
    """Return processes list"""
    app = cast("QgisWorker", _state.consumer.app)
    if app.processes_cache:
        return app.processes_cache.processes
    return []


@inspect_command(
    args=[("ident", str), ("project_path", str)],
)
def describe_process(_state, ident: str, project_path: str | None) -> dict | None:
    """Return process description"""
    app = cast("QgisWorker", _state.consumer.app)
    if app.processes_cache:
        return app.processes_cache.describe(ident, project_path)
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
    app = cast("QgisWorker", _state.consumer.app)

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


#
# Worker
#


class QgisWorker(WorkerBase, CallbacksMixin, StorageMixin, JoblogMixin):

    @staticmethod
    def load_configuration() -> ConfigProto:
        return cast("ConfigProto", load_configuration())

    def __init__(self, **kwargs) -> None:
        conf = QgisWorker.load_configuration()
        self._processing_config = conf.processing

        super().__init__(conf, **kwargs)

        self.processes_cache = None


    def start_worker(self, **kwargs):
        self.processes_cache = self.create_processes_cache()
        super().start_worker(**kwargs)

    @property
    def processing_config(self) -> ProcessingConfig:
        return self._processing_config

    @property
    def workdir(self) -> Path:
        return self._processing_config.workdir

    @property
    def store_url(self) -> Template:
        return self._processing_config.store_url

    def reload_processes(self) -> None:
        """Reload processes"""
        if self.processes_cache:
            self.processes_cache.update()

        super().reload_processes()

    def on_worker_ready(self) -> None:
        super().on_worker_ready()
        # Start process cache
        if self.processes_cache:
            self.processes_cache.update()

    def on_worker_shutdown(self) -> None:
        # Stop proccess cache
        if self.processes_cache:
            self.processes_cache.stop()
        super().on_worker_shutdown()

    def create_context(self) -> QgisContext:
        return QgisContext(self.processing_config, service_name=self.service_name)

    def create_processes_cache(self) -> Optional[ProcessCacheProtocol]:
        return None

#
# Qgis jobs
#


class QgisJob(Job):
    def update_run_context(self, task_id: str, context: dict[str, Any]):
        # Add qgis context in job context
        context.update(qgis_context=self.app.create_context())


class QgisProcessJob(ProcessJob):
    def update_run_context(self, task_id: str, context: dict[str, Any]):
        # Add qgis context in job context
        context.update(qgis_context=self.app.create_context())

    @contextmanager
    def prepare_request(self, task_id, args, kwargs):
        # Keep the request (and its subscriber) for postrun callbacks
        # if 'before_start' fails: the run configuration is removed from
        # the arguments (see GenericJob)
        request = kwargs.get("__run_config__", {}).get("request")
        try:
            yield
        finally:
            if request is not None:
                kwargs.setdefault("request", request)
