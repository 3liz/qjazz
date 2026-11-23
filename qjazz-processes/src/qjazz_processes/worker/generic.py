"""Generic worker

- Does not depend on QGIS
- Define processes from worker jobs
"""

from contextlib import contextmanager
from typing import (
    Optional,
    cast,
)
from uuid import UUID

from celery.signals import (
    worker_before_create_process,
)
from celery.worker.control import (
    inspect_command,
)

from ..schemas import (
    JsonValue,
    ProcessSummary,
    ProcessSummaryList,
)
from .celery import Job
from .mixins.callbacks import CallbacksMixin
from .mixins.joblog import JoblogMixin
from .mixins.storage import StorageMixin
from .models import (
    WorkerPresenceVersion,
)
from .service import Service, ServiceJob

#
#  Signals
#

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
                metadata=p.metadata,
                description=p.description,
            )
            for ident, p in Job.RUN_CONFIGS.items()
        ],
        mode="json",
        exclude_none=True,
        by_alias=True,
    )


@inspect_command(
    args=[("ident", str), ("project_path", str)],
)
def describe_process(_state, ident: str, project_path: str | None) -> dict | None:
    """Return process description"""
    if p := Job.RUN_CONFIGS.get(ident):
        return p.model_dump(mode="json")
    return None


@inspect_command()
def presence(_state) -> dict:
    """Returns informations about the service"""
    app = cast("GenericWorker", _state.consumer.app)
    return app.presence().model_dump()



class GenericWorker(Service, CallbacksMixin, StorageMixin, JoblogMixin):
    _class_id: Optional[UUID] = None

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


class GenericJob(ServiceJob):
    def __call__(self, *arg, **kwargs) -> JsonValue:
        # Output must be wrapped in a dictionnary in order
        # to conform to the run_config schema
        return {"output": super().__call__(*arg, **kwargs)}

    # Override
    @contextmanager
    def prepare_request(self, task_id, args, kwargs):
        # We receive argument as job processes request
        # in order to match the task signature, replace
        # the __run_config__ with the request 'inputs'
        run_config = kwargs["__run_config__"]
        request = run_config["request"]
        try:
            kwargs["__run_config__"] = request["inputs"]
            # Add the 'project_path' to the job context
            context = kwargs.get("__context__")
            if context is None:
                context = kwargs["__context__"] = {}
            context.update(project_path=run_config.get("project_path"))
            yield
        finally:
            # Keep the request for postrun callbacks and job details
            # Note: always overwrite since 'request' may be an input name
            kwargs["request"] = request
