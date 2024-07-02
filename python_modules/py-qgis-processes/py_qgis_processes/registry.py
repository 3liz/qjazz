#
# Register/Retrieve launched jobs
# by id/service/realm/
#
from dataclasses import dataclass
from time import time

from typing_extensions import (
    Iterator,
    Mapping,
    Optional,
    Tuple,
)

from .celery import Celery
from .processing.schemas import JobStatus


@dataclass
class TaskInfo:
    job_id: str
    created: int
    service: str
    realm: Optional[str]
    process_id: str
    dismissed: int


def register(
    app: Celery,
    service: str,
    realm: Optional[str],
    status: JobStatus,
    expires: int,
):
    key = f"py-qgis::{status.job_id}::{service}::{realm}"

    client = app.backend.client
    client.hset(
        key,
        mapping=dict(
            job_id=status.job_id,
            created=int(status.created.timestamp()),
            service=service,
            realm=realm or "",
            process_id=status.process_id,
            dismissed=0,
        ),
    )
    client.expireat(key, int(time()) + expires)


def _decode(m: Mapping[bytes, bytes]) -> TaskInfo:
    return TaskInfo(
        job_id=m[b'job_id'].decode(),
        created=int(m[b'created']),
        service=m[b'service'].decode(),
        realm=m[b'realm'].decode(),
        process_id=m[b'process_id'].decode(),
        dismissed=int(m[b'dismissed']),
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
    cursor: int = 0,
    count: int = 100,  # Minimal count hint
) -> Tuple[int, Iterator[Tuple[str, str, str]]]:
    """ Iterate over filtered task infos
    """
    client = app.backend.client
    pattern = f"py-qgis::*::{service or '*'}::{realm or '*'}"
    cursor, keys = client.scan(cursor=cursor, match=pattern, count=count)
    return cursor, (tuple(key.decode().split("::")[1:4]) for key in keys)


def dismiss(app: Celery, job_id: str) -> bool:
    """ Set state to 'dismissed'
    """
    client = app.backend.client
    keys = client.keys(f"py-qgis::{job_id}::*")
    if keys:
        client.hset(keys[0], 'dismissed', 1)
        return True
    else:
        return False


def delete(app: Celery, job_id: str) -> Optional[TaskInfo]:
    """ Delete task info
    """
    client = app.backend.client
    keys = client.keys(f"py-qgis::{job_id}::*")
    if keys:
        data = client.hgetall(keys[0])
        client.delete(keys[0])
        return _decode(data)
    else:
        return None
