from datetime import datetime, timezone
from fnmatch import fnmatchcase
from types import SimpleNamespace
from typing import Iterator, cast

import pytest

from qjazz_core.celery import Celery

from qjazz_processes.schemas import JobStatus
from qjazz_processes.worker import registry


class FakeRedis:
    """Record the key patterns sent to redis"""

    def __init__(self):
        self.patterns: list[str] = []
        # Keys returned by 'keys()'
        self.existing: list[bytes] = []
        self.expires: dict[bytes, int] = {}

    def keys(self, pattern: str) -> list[bytes]:
        self.patterns.append(pattern)
        return self.existing

    def hset(self, key, *args, **kwargs):
        self.patterns.append(key)

    def expireat(self, key, ts):
        pass

    def expire(self, key: bytes, timeout: int):
        self.expires[key] = timeout


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


def test_registry_set_expiration(app: Celery, client: FakeRedis):
    job_id = "6f1d2b9e-3c1a-4d7e-9a0b-2f5c8e1d4a7b"

    # Job not registered
    assert registry.set_expiration(app, job_id, 900) is False
    assert client.patterns == [f"qjazz::{job_id}::*"]
    assert client.expires == {}

    # Registered job
    key = f"qjazz::{job_id}::test::None".encode()
    client.existing = [key]
    assert registry.set_expiration(app, job_id, 900) is True
    assert client.expires == {key: 900}


def test_registry_set_expiration_invalid_job_id(app: Celery, client: FakeRedis):
    assert registry.set_expiration(app, "*", 900) is False
    assert client.patterns == []


class StoreRedis:
    """In-memory registry store with redis glob matching"""

    def __init__(self):
        self.store: dict[str, dict] = {}

    def hset(self, key, mapping=None, **kwargs):
        self.store.setdefault(key, {}).update(mapping or {})

    def expireat(self, key, ts):
        pass

    def hgetall(self, key: str | bytes) -> dict[bytes, bytes]:
        key = key.decode() if isinstance(key, bytes) else key
        return {k.encode(): str(v).encode() for k, v in self.store.get(key, {}).items()}

    def keys(self, pattern: str) -> list[bytes]:
        return [k.encode() for k in self.store if fnmatchcase(k, pattern)]

    def scan_iter(self, match: str) -> Iterator[bytes]:
        return iter(self.keys(match))


def _register(app: Celery, job_id: str, realm: str | None):
    status = JobStatus(
        job_id=job_id,
        process_id="test",
        status=JobStatus.PENDING,
        created=datetime.now(timezone.utc),
    )
    registry.register(app, "test", realm, status, expires=10, pending_timeout=10)


def test_registry_job_without_realm():
    """Jobs without realm have an empty realm segment"""
    client = StoreRedis()
    app = cast("Celery", SimpleNamespace(backend=SimpleNamespace(client=client)))

    no_realm = "6f1d2b9e-3c1a-4d7e-9a0b-2f5c8e1d4a7b"
    with_realm = "1a2b3c4d-0000-4000-8000-000000000001"
    _register(app, no_realm, None)
    _register(app, with_realm, "realm_owner_01")

    assert set(client.store) == {
        f"qjazz::{no_realm}::test::",
        f"qjazz::{with_realm}::test::realm_owner_01",
    }

    # Found without realm
    ti = registry.find_job(app, no_realm)
    assert ti is not None
    assert ti.realm == ""
    assert registry.exists(app, no_realm)
    assert registry.exists(app, no_realm, service="test")

    # Not found with a realm
    assert registry.find_job(app, no_realm, realm="realm_owner_01") is None
    # Literal 'None' realm does not match jobs without realm
    assert registry.find_job(app, no_realm, realm="None") is None

    # Listing without realm returns all jobs, with a realm only its jobs
    assert {ti.job_id for ti in registry.iter_jobs(app)} == {no_realm, with_realm}
    assert {ti.job_id for ti in registry.iter_jobs(app, realm="realm_owner_01")} == {with_realm}
