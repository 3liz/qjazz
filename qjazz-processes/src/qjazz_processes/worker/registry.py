#
# Register/Retrieve launched jobs
# by id/service/realm/
#
import re

from dataclasses import dataclass
from typing import (
    Iterator,
    Mapping,
    Optional,
)

import redis

from qjazz_core.celery import Celery

from ..schemas import JobStatus

# Job ids are used for building redis key patterns:
# restrict to characters that have no special meaning in glob patterns
JOB_ID_PATTERN = r"[A-Za-z0-9_-]+"

_JOB_ID_MATCH = re.compile(JOB_ID_PATTERN)


def is_valid_job_id(job_id: str) -> bool:
    """Check that job id is made of alphanumeric, dash or underscore chars"""
    return _JOB_ID_MATCH.fullmatch(job_id) is not None


@dataclass
class TaskInfo:
    job_id: str
    created: int
    service: str
    realm: Optional[str]
    process_id: str
    dismissed: int
    pending_timeout: int
    expires: int
    tag: Optional[str]


def register(
    app: Celery,
    service: str,
    realm: Optional[str],
    status: JobStatus,
    expires: int,
    pending_timeout: int,
):
    if not is_valid_job_id(status.job_id):
        raise ValueError(f"Invalid job id: {status.job_id!r}")

    key = f"qjazz::{status.job_id}::{service}::{realm}"

    created = int(status.created.timestamp())

    client = app.backend.client
    client.hset(
        key,
        mapping={
            "job_id": status.job_id,
            "created": created,
            "service": service,
            "realm": realm or "",
            "process_id": status.process_id,
            "dismissed": 0,
            "pending_timeout": pending_timeout,
            "expires": expires,
            "tag": status.tag or "",
        },
    )
    expiration_ts = created + expires + pending_timeout
    # Set expiration upper bound for pending job:
    # expiration is updated when the job starts and when it finishes
    # (see 'set_expiration')
    client.expireat(key, expiration_ts)


def set_expiration(app: Celery, job_id: str, timeout: int) -> bool:
    """Set the job entry to expire in `timeout` seconds from now

    Returns False if the job is not registered (i.e dismissed or expired)
    """
    if not is_valid_job_id(job_id):
        return False
    client = app.backend.client
    keys = client.keys(f"qjazz::{job_id}::*")
    for key in keys:
        client.expire(key, timeout)
    return bool(keys)


def _decode(m: Mapping[bytes, bytes]) -> TaskInfo:
    return TaskInfo(
        job_id=m[b"job_id"].decode(),
        created=int(m[b"created"]),
        service=m[b"service"].decode(),
        realm=m[b"realm"].decode(),
        process_id=m[b"process_id"].decode(),
        dismissed=int(m[b"dismissed"]),
        pending_timeout=int(m[b"pending_timeout"]),
        expires=int(m[b"expires"]),
        tag=m[b"tag"].decode(),
    )


def find_job(
    app: Celery,
    job_id: str,
    *,
    realm: Optional[str] = None,
) -> Optional[TaskInfo]:
    """Return single task info"""
    if not is_valid_job_id(job_id):
        return None
    client = app.backend.client
    keys = client.keys(f"qjazz::{job_id}::*::{realm or '*'}")
    if keys:
        return _decode(client.hgetall(keys[0]))
    return None


def find_key(
    app: Celery,
    job_id: str,
    *,
    realm: Optional[str] = None,
) -> Optional[tuple[str, str, str]]:
    if not is_valid_job_id(job_id):
        return None
    client = app.backend.client
    keys = client.keys(f"qjazz::{job_id}::*::{realm or '*'}")
    if keys:
        return tuple(keys[0].decode().split("::")[1:4])
    return None


def find_keys(
    app: Celery,
    service: Optional[str] = None,
    *,
    realm: Optional[str] = None,
) -> Iterator[tuple[str, str, str]]:
    """Iterate over filtered task infos"""
    client = app.backend.client
    pattern = f"qjazz::*::{service or '*'}::{realm or '*'}"
    keys = client.scan_iter(match=pattern)
    return (tuple(key.decode().split("::")[1:4]) for key in keys)


def iter_jobs(
    app: Celery,
    service: Optional[str] = None,
    *,
    realm: Optional[str] = None,
) -> Iterator[TaskInfo]:
    client = app.backend.client
    pattern = f"qjazz::*::{service or '*'}::{realm or '*'}"
    keys = client.scan_iter(match=pattern)
    for key in keys:
        yield _decode(client.hgetall(key))


def dismiss(app: Celery, job_id: str, reset: bool = False) -> bool:
    """Set state to 'dismissed'"""
    if not is_valid_job_id(job_id):
        return False
    client = app.backend.client
    keys = client.keys(f"qjazz::{job_id}::*")
    if keys:
        client.hset(keys[0], "dismissed", 0 if reset else 1)
        return True
    return False


def delete(app: Celery, job_id: str) -> int:
    """Delete task info"""
    if not is_valid_job_id(job_id):
        return 0
    client = app.backend.client
    keys = client.keys(f"qjazz::{job_id}::*")
    if keys:
        client.delete(*keys)
        return 1
    return 0


def lock(
    app: Celery,
    name: str,
    timeout: Optional[int],
    expires: Optional[int] = None,
) -> redis.lock.Lock:
    """Return a redis Lock"""
    return app.backend.client.lock(
        f"lock:{name}",
        blocking_timeout=timeout,
        timeout=expires,
        sleep=1,
    )


def exists(app: Celery, job_id: str, *, service: Optional[str] = None) -> bool:
    """Check if a job is registred"""
    if not is_valid_job_id(job_id):
        return False
    return bool(app.backend.client.keys(f"qjazz::{job_id}::{service or '*'}"))
