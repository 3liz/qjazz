#
# Register/Retrieve launched jobs
# by id/service/realm/
#
from dataclasses import dataclass

import redis

from typing_extensions import (
    Iterator,
    Mapping,
    Optional,
    Tuple,
)

from py_qgis_contrib.core.celery import Celery

from ..schemas import JobStatus


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


def register(
    app: Celery,
    service: str,
    realm: Optional[str],
    status: JobStatus,
    expires: int,
    pending_timeout: int,
):
    key = f"py-qgis::{status.job_id}::{service}::{realm}"

    created = int(status.created.timestamp())

    client = app.backend.client
    client.hset(
        key,
        mapping=dict(
            job_id=status.job_id,
            created=created,
            service=service,
            realm=realm or "",
            process_id=status.process_id,
            dismissed=0,
            pending_timeout=pending_timeout,
            expires=expires,
        ),
    )
    expiration_ts = created + expires + pending_timeout
    # Set expiration upper bound
    client.expireat(key, expiration_ts)


def _decode(m: Mapping[bytes, bytes]) -> TaskInfo:
    return TaskInfo(
        job_id=m[b'job_id'].decode(),
        created=int(m[b'created']),
        service=m[b'service'].decode(),
        realm=m[b'realm'].decode(),
        process_id=m[b'process_id'].decode(),
        dismissed=int(m[b'dismissed']),
        pending_timeout=int(m[b'pending_timeout']),
        expires=int(m[b'expires']),
    )


def find_job(
    app: Celery,
    job_id: str,
    *,
    realm: Optional[str] = None,
) -> Optional[TaskInfo]:
    """ Return single task info
    """
    client = app.backend.client
    keys = client.keys(f"py-qgis::{job_id}::*::{realm or '*'}")
    if keys:
        return _decode(client.hgetall(keys[0]))
    else:
        return None


def find_key(
    app: Celery,
    job_id: str,
    *,
    realm: Optional[str] = None,
) -> Optional[Tuple[str, str, str]]:
    client = app.backend.client
    keys = client.keys(f"py-qgis::{job_id}::*::{realm or '*'}")
    if keys:
        return tuple(keys[0].split('::')[1:4])
    else:
        return None


def find_keys(
    app: Celery,
    service: Optional[str] = None,
    *,
    realm: Optional[str] = None,
) -> Iterator[Tuple[str, str, str]]:
    """ Iterate over filtered task infos
    """
    client = app.backend.client
    pattern = f"py-qgis::*::{service or '*'}::{realm or '*'}"
    keys = client.scan_iter(match=pattern)
    return (tuple(key.decode().split("::")[1:4]) for key in keys)


def iter_jobs(
    app: Celery,
    service: Optional[str] = None,
    *,
    realm: Optional[str] = None,
) -> Iterator[TaskInfo]:

    client = app.backend.client
    pattern = f"py-qgis::*::{service or '*'}::{realm or '*'}"
    keys = client.scan_iter(match=pattern)
    for key in keys:
        yield _decode(client.hgetall(key))


def dismiss(app: Celery, job_id: str, reset: bool = False) -> bool:
    """ Set state to 'dismissed'
    """
    client = app.backend.client
    keys = client.keys(f"py-qgis::{job_id}::*")
    if keys:
        client.hset(keys[0], 'dismissed', 0 if reset else 1)
        return True
    else:
        return False


def delete(app: Celery, job_id: str) -> int:
    """ Delete task info
    """
    client = app.backend.client
    keys = client.keys(f"py-qgis::{job_id}::*")
    if keys:
        client.delete(*keys)
        return 1
    else:
        return 0


def lock(
    app: Celery,
    name: str,
    timeout: Optional[int],
    expires: Optional[int] = None,
) -> redis.lock.Lock:
    """ Return a redis Lock
    """
    return app.backend.client.lock(
        f"lock:{name}",
        blocking_timeout=timeout,
        timeout=expires,
        sleep=1,
    )


def exists(app: Celery, job_id: str) -> bool:
    """ Check if a job is registred
    """
    return bool(app.backend.client.keys(f"py-qgis::{job_id}::*"))
