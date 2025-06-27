from typing import (
    Mapping,
    Protocol,
    Sequence,
)

import celery

from celery.signals import (
    task_postrun,
    task_prerun,
)
from pydantic import TypeAdapter

from ...callbacks import Callbacks
from ...schemas import JobResults, Subscriber


class CallbacksProto(Protocol):
    @property
    def processes_callbacks(self) -> Callbacks: ...


MaybeSubscriber: TypeAdapter = TypeAdapter(Subscriber | None)


# Used as marker trait
class CallbacksMixin(CallbacksProto):
    pass


#
# Callbacks
#


@task_prerun.connect
def on_task_prerun(
    sender: object,
    task_id: str,
    task: celery.Task,
    args: Sequence,
    kwargs: Mapping,
    **_,
):
    request = kwargs["__run_config__"]["request"]
    subscriber = MaybeSubscriber.validate_python(request.get("subscriber"))

    if subscriber and subscriber.in_progress_uri:
        task.app.processes_callbacks.in_progress(
            str(subscriber.in_progress_uri),
            task_id,
            kwargs["__meta__"],
        )


@task_postrun.connect
def on_task_postrun(
    sender: object,
    task_id: str,
    task: celery.Task,
    args: Sequence,
    kwargs: Mapping,
    retval: JobResults,
    state: str,
    **_,
):
    task.app.task_postrun_callbacks(task_id, state, retval, kwargs)

    subscriber = MaybeSubscriber.validate_python(kwargs["request"].get("subscriber"))
    if not subscriber:
        return

    match state:
        case celery.states.SUCCESS if subscriber.success_uri:
            task.app.processes_callbacks.on_success(
                str(subscriber.success_uri),
                task_id,
                kwargs["__meta__"],
                retval,
            )
        case celery.states.FAILURE if subscriber.failed_uri:
            task.app.processes_callbacks.on_failure(
                str(subscriber.failed_uri),
                task_id,
                kwargs["__meta__"],
            )
