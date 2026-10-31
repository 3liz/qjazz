#
# Test job registration on execution
#
from contextlib import nullcontext
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from time import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

from qjazz_core.utils import to_utc_datetime

from qjazz_processes.executor.executor import ExecutorBase
from qjazz_processes.executor.processes import Processes
from qjazz_processes.schemas import JobExecute, JobStatus
from qjazz_processes.worker import registry

if TYPE_CHECKING:
    from qjazz_core.celery import Celery

    from qjazz_processes.executor.protocols import ServiceDict


class FakeRedis:
    """Minimal in-memory redis registry"""

    def __init__(self):
        self.store: dict[str, dict] = {}

    def hset(self, key, field=None, value=None, mapping=None):
        key = key.decode() if isinstance(key, bytes) else key
        item = self.store.setdefault(key, {})
        if field is not None:
            item[field] = value
        item.update(mapping or {})

    def lock(self, name, **kwargs):
        return nullcontext()

    def expireat(self, key, ts):
        pass

    def hgetall(self, key: str | bytes) -> dict[bytes, bytes]:
        key = key.decode() if isinstance(key, bytes) else key
        return {k.encode(): str(v).encode() for k, v in self.store.get(key, {}).items()}

    def keys(self, pattern: str) -> list[bytes]:
        return [k.encode() for k in self.store if fnmatchcase(k, pattern)]

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k.decode() if isinstance(k, bytes) else k, None)


class FakeCelery:
    """Record the registry state when the task is sent"""

    def __init__(self, fail: bool = False):
        self.backend = SimpleNamespace(client=FakeRedis())
        self.fail = fail
        self.sent: list[dict] = []

    def send_task(self, name, task_id=None, **kwargs):
        # Like Celery, generate a task id if none is given
        task_id = task_id or str(uuid4())
        registered = registry.find_job(cast("Celery", self), task_id) is not None
        self.sent.append(
            {
                "name": name,
                "task_id": task_id,
                "registered": registered,
                "priority": kwargs.get("priority"),
            },
        )
        if self.fail:
            raise ConnectionError("Broker unavailable")
        return SimpleNamespace(id=task_id)


def _executor(celery: FakeCelery, destinations: tuple[str, ...] = ()) -> Processes:
    # Bare executor instance with only the attributes required for execution
    executor = cast("Processes", object.__new__(cast("type", Processes)))
    executor._celery = cast("Celery", celery)
    executor._pending_expiration_timeout = 600
    # Use the concrete implementation from the executor
    executor.get_destinations = ExecutorBase.get_destinations  # type: ignore [method-assign]
    executor._services = cast(
        "ServiceDict",
        {"test": (destinations, SimpleNamespace(result_expires=900, entrypoint="process_execute"))},
    )
    return executor


def test_executor_register_before_send():
    """Job is registered before the task is sent"""
    celery = FakeCelery()
    executor = _executor(celery)

    job_id, _, _ = executor._execute("test", "processes_test:testsimplevalue", JobExecute(inputs={}))

    assert len(celery.sent) == 1
    sent = celery.sent[0]
    assert sent["name"] == "test.process_execute"
    # The task id is the registered job id
    assert sent["task_id"] == job_id
    # Job was registered when the task was sent
    assert sent["registered"]
    assert registry.find_job(cast("Celery", celery), job_id) is not None


def test_executor_register_send_failure():
    """Job is unregistered if the task cannot be sent"""
    celery = FakeCelery(fail=True)
    executor = _executor(celery)

    with pytest.raises(ConnectionError):
        executor._execute("test", "processes_test:testsimplevalue", JobExecute(inputs={}))

    assert len(celery.sent) == 1
    assert celery.sent[0]["registered"]
    # No job left in registry
    assert celery.backend.client.store == {}


def test_executor_priority():
    """Job priority is passed to the task"""
    celery = FakeCelery()
    executor = _executor(celery)

    executor._execute(
        "test",
        "processes_test:testsimplevalue",
        JobExecute(inputs={}),
        priority=7,
    )
    assert celery.sent[0]["priority"] == 7

    # Default priority
    executor._execute("test", "processes_test:testsimplevalue", JobExecute(inputs={}))
    assert celery.sent[1]["priority"] == 0


def test_executor_unknown_job():
    """Unknown job returns None (i.e 404) for job commands"""
    celery = FakeCelery()
    executor = _executor(celery)

    job_id = "6f1d2b9e-3c1a-4d7e-9a0b-2f5c8e1d4a7b"

    assert executor._log_details(job_id, executor._services, timeout=1) is None
    assert executor._files(job_id, executor._services, public_url=None, timeout=1) is None
    assert (
        executor._download_url(
            job_id,
            executor._services,
            resource="output.json",
            timeout=1,
            expiration=60,
        )
        is None
    )


def test_executor_dismiss_failure_resets_state():
    """A failure while dismissing a job resets its dismissed state"""
    celery = FakeCelery()
    executor = _executor(celery, destinations=("test@worker",))

    job_id, _, _ = executor._execute("test", "processes_test:testsimplevalue", JobExecute(inputs={}))

    def get_task_meta(task_id):
        raise ConnectionError("Result backend unavailable")

    celery.backend.get_task_meta = get_task_meta

    with pytest.raises(ConnectionError):
        executor._dismiss(job_id, executor._services, realm=None)

    ti = registry.find_job(cast("Celery", celery), job_id)
    assert ti is not None
    # Job is not left as dismissed
    assert ti.dismissed == 0


#
# Query task infos from workers
#

JOB_ID = "6f1d2b9e-3c1a-4d7e-9a0b-2f5c8e1d4a7b"


def _query_task_replies(
    celery: FakeCelery,
    replies: dict | None,
    scheduled: dict | None = None,
):
    # 'inspect().query_task()' and 'inspect().scheduled()' replies, keyed by worker
    celery.revoked = []  # type: ignore [attr-defined]
    # Record the inspect commands sent
    celery.inspected = []  # type: ignore [attr-defined]

    def _query_task(*ids):
        celery.inspected.append("query_task")  # type: ignore [attr-defined]
        return replies

    def _scheduled():
        celery.inspected.append("scheduled")  # type: ignore [attr-defined]
        return scheduled

    celery.control = SimpleNamespace(  # type: ignore [attr-defined]
        inspect=lambda destination=None: SimpleNamespace(
            query_task=_query_task,
            scheduled=_scheduled,
        ),
        revoke=lambda task_id, **kwargs: celery.revoked.append(task_id),  # type: ignore [attr-defined]
    )


def _task_infos() -> dict:
    return {
        "id": JOB_ID,
        "kwargs": {
            "__meta__": {
                "process_id": "processes_test:testsimplevalue",
                "created": datetime.now(timezone.utc).isoformat(),
            },
        },
    }


@pytest.mark.parametrize(
    "workers",
    [
        # The worker holding the task replies first, last or alone
        ("test@node-b", "test@node-a"),
        ("test@node-a", "test@node-b"),
        ("test@node-b",),
    ],
)
def test_executor_query_task_multiple_workers(workers):
    """Infos are returned from the worker holding the task"""
    celery = FakeCelery()
    executor = _executor(celery, destinations=workers)

    infos = _task_infos()
    _query_task_replies(
        celery,
        {w: ({JOB_ID: ["reserved", infos]} if w == "test@node-b" else {}) for w in workers},
    )

    assert executor._query_task(JOB_ID, workers) == ("reserved", infos)


@pytest.mark.parametrize("replies", [None, {}, {"test@node-a": {}, "test@node-b": {}}])
def test_executor_query_task_not_found(replies):
    """No worker holds the task"""
    celery = FakeCelery()
    executor = _executor(celery)

    _query_task_replies(celery, replies)

    assert executor._query_task(JOB_ID) == (None, None)


def test_executor_query_task_invalid_format():
    celery = FakeCelery()
    executor = _executor(celery)

    _query_task_replies(celery, {"test@node-a": {}, "test@node-b": {JOB_ID: "reserved"}})

    with pytest.raises(ValueError, match="Invalid format"):
        executor._query_task(JOB_ID)


def test_executor_job_status_reserved_on_other_worker():
    """A job reserved by a worker that does not reply first is 'accepted'"""
    celery = FakeCelery()
    workers = ("test@node-a", "test@node-b")
    executor = _executor(celery, destinations=workers)

    # No backend state yet
    celery.backend.get_task_meta = lambda task_id: {"status": "PENDING"}
    _query_task_replies(
        celery,
        {"test@node-a": {}, "test@node-b": {JOB_ID: ["reserved", _task_infos()]}},
    )

    status = executor._job_status(JOB_ID, workers)
    assert status is not None
    assert status.status == JobStatus.ACCEPTED
    assert status.message == "Task accepted"


def _scheduled_replies(infos: dict) -> dict:
    # Delayed job held in the timer of the second worker
    return {
        "test@node-a": [],
        "test@node-b": [{"eta": "2026-10-31T19:00:00+00:00", "priority": 0, "request": infos}],
    }


def test_executor_query_task_scheduled():
    """Delayed jobs are found in the scheduled tasks"""
    celery = FakeCelery()
    workers = ("test@node-a", "test@node-b")
    executor = _executor(celery, destinations=workers)

    infos = _task_infos()
    # 'query_task' does not report tasks with an ETA
    _query_task_replies(celery, {w: {} for w in workers}, _scheduled_replies(infos))

    eta = int(time()) + 30
    assert executor._query_task(JOB_ID, workers, eta=eta) == ("scheduled", infos)
    # 'query_task' does not report tasks before their ETA
    assert celery.inspected == ["scheduled"]  # type: ignore [attr-defined]


def test_executor_job_status_scheduled():
    """A delayed job is 'accepted'"""
    celery = FakeCelery()
    workers = ("test@node-a", "test@node-b")
    executor = _executor(celery, destinations=workers)

    celery.backend.get_task_meta = lambda task_id: {"status": "PENDING"}
    _query_task_replies(celery, {w: {} for w in workers}, _scheduled_replies(_task_infos()))

    eta = int(time()) + 30
    status = executor._job_status(JOB_ID, workers, eta=eta)
    assert status is not None
    assert status.status == JobStatus.ACCEPTED
    assert status.message == f"Task scheduled at {to_utc_datetime(eta).isoformat()}"


def test_executor_dismiss_scheduled_job():
    """Dismissing a delayed job revokes it"""
    celery = FakeCelery()
    workers = ("test@node-a", "test@node-b")
    executor = _executor(celery, destinations=workers)

    job_id, _, _ = executor._execute(
        "test",
        "processes_test:testsimplevalue",
        JobExecute(inputs={}),
        countdown=30,
    )

    # The ETA is registered with the job
    ti = registry.find_job(cast("Celery", celery), job_id)
    assert ti is not None
    assert ti.eta == ti.created + 30

    infos = _task_infos() | {"id": job_id}
    celery.backend.get_task_meta = lambda task_id: {"status": "PENDING"}
    _query_task_replies(celery, {w: {} for w in workers}, _scheduled_replies(infos))

    status = executor._dismiss(job_id, executor._services, realm=None)
    assert status is not None
    assert status.status == JobStatus.DISMISSED

    assert celery.revoked == [job_id]  # type: ignore [attr-defined]
    assert registry.find_job(cast("Celery", celery), job_id) is None


@pytest.mark.parametrize(
    "eta_offset,expected",
    [
        # No ETA: the task is reserved or active
        (None, ["query_task"]),
        # Before the ETA: the task is in the worker's timer
        (30, ["scheduled"]),
        # Just after the ETA: the task may still be in the worker's timer
        (-5, ["query_task", "scheduled"]),
        # Past the grace period
        (-60, ["query_task"]),
    ],
)
def test_executor_query_task_inspect_commands(eta_offset, expected):
    """The registered ETA selects the inspect commands"""
    celery = FakeCelery()
    executor = _executor(celery)

    _query_task_replies(celery, {}, {})

    eta = int(time()) + eta_offset if eta_offset is not None else None
    assert executor._query_task(JOB_ID, eta=eta) == (None, None)
    assert celery.inspected == expected  # type: ignore [attr-defined]


def test_registry_no_eta():
    """Jobs without delay are registered without ETA"""
    celery = FakeCelery()
    executor = _executor(celery)

    job_id, _, _ = executor._execute("test", "processes_test:testsimplevalue", JobExecute(inputs={}))
    ti = registry.find_job(cast("Celery", celery), job_id)
    assert ti is not None
    assert ti.eta is None
