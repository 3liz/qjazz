from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast

import pytest

from qjazz_core.celery import Celery

from qjazz_processes.schemas import JobStatus
from qjazz_processes.worker import registry


class FakeRedis:
    """Record the key patterns sent to redis"""

    def __init__(self):
        self.patterns: list[str] = []

    def keys(self, pattern: str) -> list[bytes]:
        self.patterns.append(pattern)
        return []

    def hset(self, key, *args, **kwargs):
        self.patterns.append(key)

    def expireat(self, key, ts):
        pass


@pytest.fixture()
def client() -> FakeRedis:
    return FakeRedis()


@pytest.fixture()
def app(client: FakeRedis) -> Celery:
    # Fake Celery app with a fake redis backend client
    return cast("Celery", SimpleNamespace(backend=SimpleNamespace(client=client)))


@pytest.mark.parametrize(
    "job_id",
    [
        "6f1d2b9e-3c1a-4d7e-9a0b-2f5c8e1d4a7b",
        "job_01",
        "ABC-def_123",
    ],
)
def test_registry_valid_job_id(job_id: str):
    assert registry.is_valid_job_id(job_id)


@pytest.mark.parametrize(
    "job_id",
    [
        "",
        "*",
        "?",
        "[a-z]*",
        "job*",
        "job\\*",
        "job::test",
        "job/../x",
        "job id",
    ],
)
def test_registry_invalid_job_id(job_id: str, app: Celery, client: FakeRedis):
    assert not registry.is_valid_job_id(job_id)

    # Lookups must not reach redis with an invalid job id
    assert registry.find_job(app, job_id) is None
    assert registry.find_key(app, job_id) is None
    assert registry.dismiss(app, job_id) is False
    assert registry.delete(app, job_id) == 0
    assert registry.exists(app, job_id) is False

    assert client.patterns == []


def test_registry_lookup_pattern(app: Celery, client: FakeRedis):
    job_id = "6f1d2b9e-3c1a-4d7e-9a0b-2f5c8e1d4a7b"

    registry.delete(app, job_id)
    assert client.patterns == [f"qjazz::{job_id}::*"]


def test_registry_register_invalid_job_id(app: Celery, client: FakeRedis):
    status = JobStatus(
        job_id="*",
        process_id="test",
        status=JobStatus.PENDING,
        created=datetime.now(timezone.utc),
    )
    with pytest.raises(ValueError):
        registry.register(app, "test", None, status, expires=10, pending_timeout=10)

    assert client.patterns == []
