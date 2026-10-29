#
# Test job registration on execution
#
from contextlib import nullcontext
from fnmatch import fnmatchcase
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest

from qjazz_processes.executor.executor import ExecutorBase
from qjazz_processes.executor.processes import Processes
from qjazz_processes.schemas import JobExecute
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
