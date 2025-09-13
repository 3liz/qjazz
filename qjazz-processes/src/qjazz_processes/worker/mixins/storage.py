import shutil

from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Protocol,
    cast,
)

import redis

from celery.worker.control import (
    control_command,
    inspect_command,
)
from qjazz_core import logger

from .. import registry
from ..models import Link
from ..storage import Storage

# Type only imports
if TYPE_CHECKING:
    from qjazz_core.celery import Worker


class BackendProto(Protocol):
    client: redis.Redis


class StorageProto(Protocol):
    _workdir: Path
    _storage: Storage

    @property
    def service_name(self) -> str: ...
    @property
    def backend(self) -> BackendProto: ...
    def cleanup_expired_jobs(self) -> None: ...
    def download_url(self, job_id: str, resource: str, expiration: int) -> Link: ...


#
# Controls
#


@control_command()
def cleanup(state):
    """Run cleanup task"""
    app = cast("StorageProto", state.consumer.app)
    app.cleanup_expired_jobs()


#
# Inspect
#


@inspect_command(
    args=[("job_id", str), ("resource", str), ("expiration", int)],
)
def download_url(state, job_id, resource, expiration):
    try:
        app = cast("StorageProto", state.consumer.app)
        return app.download_url(
            job_id,
            resource,
            expiration,
        ).model_dump()
    except FileNotFoundError as err:
        logger.error(err)
        return None


# Used as marker trait
class StorageMixin(StorageProto):
    def download_url(self, job_id: str, resource: str, expiration: int) -> Link:
        """Returns a temporary download url"""
        return self._storage.download_url(
            job_id,
            resource,
            workdir=self._workdir,
            expires=expiration,
        )

    def cleanup_expired_jobs(self) -> None:
        """Cleanup all expired jobs"""
        try:
            with self.lock("cleanup-batch"):
                logger.trace("Running cleanup task")
                # Search for expirable jobs resources
                for p in self._workdir.glob(f"*/.job-expire-{self.service_name}"):
                    jobdir = p.parent
                    job_id = jobdir.name
                    if registry.exists(cast("Worker", self), job_id):
                        continue

                    logger.info("=== Cleaning jobs resource: %s", job_id)
                    self._storage.remove(job_id, workdir=self._workdir)

                    try:
                        shutil.rmtree(jobdir)
                    except Exception as err:
                        logger.error("Failed to remove directory '%s': %s", jobdir, err)

        except redis.lock.LockError:
            pass

    def lock(self, name: str) -> redis.lock.Lock:
        # Create a redis lock for handling race conditions
        # with multiple workers
        # See https://redis-py-doc.readthedocs.io/en/master/#redis.Redis.lock
        # The lock will hold only for 20s
        # so operation using the lock should not exceed this duration.
        return self.backend.client.lock(
            f"lock:{self.service_name}:{name}",
            blocking_timeout=0,  # Do not block
            timeout=60,  # Hold lock 1mn max
        )
