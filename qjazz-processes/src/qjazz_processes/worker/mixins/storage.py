import mimetypes
import shutil

from itertools import chain
from pathlib import Path
from string import Template
from typing import (
    TYPE_CHECKING,
    Iterable,
    Iterator,
    Optional,
    Protocol,
    Sequence,
    cast,
)

import redis

from celery.worker.control import (
    control_command,
    inspect_command,
)
from pydantic import TypeAdapter
from qjazz_core import logger
from qjazz_core.condition import assert_precondition

from .. import registry
from ..config import JobConfig
from ..models import (
    Link,
    ProcessFilesVersion,
)
from ..storage import Storage

# Type only imports
if TYPE_CHECKING:
    from ..celery import Worker

class BackendProto(Protocol):
    client: redis.Redis


class StorageProto(Protocol):
    @property
    def service_name(self) -> str: ...
    @property
    def backend(self) -> BackendProto: ...


LinkSequence: TypeAdapter[Sequence[Link]] = TypeAdapter(Sequence[Link])

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


FILE_LINKS = "links.json"


# Used as marker trait
class StorageMixin(StorageProto):

    _workdir: Path
    _store_url: Template
    _storage: Storage

    def init_storage(self, workdir: Path, store_url: Template,  storage: Storage):
        self._workdir = workdir
        self._store_url = store_url

        assert_precondition(not hasattr(StorageMixin, "_storage"))
        StorageMixin._storage = storage

    def download_url(self, job_id: str, resource: str, expiration: int) -> Link:
        """Returns a temporary download url"""
        return self._storage.download_url(
            job_id,
            resource,
            workdir=self._workdir,
            expires=expiration,
        )

    def store_reference_url(self, job_id: str, resource: str, public_url: Optional[str]) -> str:
        """Return a proper reference url for the resource"""
        return store_reference_url(
            self._store_url,
            job_id,
            resource,
            public_url,
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

    def job_files(self, job_id: str, public_url: str | None) -> ProcessFilesVersion:
        """Returns job execution files"""
        p = self._workdir.joinpath(job_id, FILE_LINKS)
        if p.exists():
            with p.open() as f:
                links = LinkSequence.validate_json(f.read())

            # Update reference according to the given public_url
            def update_ref(link: Link) -> Link:
                href = self.store_reference_url(job_id, link.title, public_url)
                return link.model_copy(update={"href": href})

            files = ProcessFilesVersion(links=tuple(update_ref(link) for link in links))
        else:
            files = ProcessFilesVersion(links=())

        return files

    def store_files(self, job_id: str, add_auxiliary_files: bool = True):
        """Move files to storage

        If add_auxiliary_files is false then all attached files created
        by the jobs are ignored and only published files are transferred.
        """
        jobdir = self._workdir.joinpath(job_id)
        files = tuple(StorageContext.published_files(jobdir))

        # Write the downloadables file links
        def _make_links() -> Iterator[Link]:
            for p in files:
                # Drop non-relative files to current
                # workdir since we don't know how to
                # download them
                if not p.is_relative_to(jobdir):
                    continue

                name = str(p.relative_to(jobdir))
                content_type = mimetypes.types_map.get(p.suffix)
                size = p.stat().st_size
                yield Link(
                    href=self.store_reference_url(job_id, name, "$public_url"),
                    mime_type=content_type or "application/octet-stream",
                    length=size,
                    title=name,
                )

        with jobdir.joinpath(FILE_LINKS).open("w") as f:
            f.write(LinkSequence.dump_json(tuple(_make_links())).decode())

        files_to_store: Iterable[Path]
        if add_auxiliary_files:
            files_to_store = chain(
                files,
                jobdir.glob("**/*.zip"),
                jobdir.glob("**/*.qgs"),
                jobdir.glob("**/*.qgz"),
                jobdir.glob("**/*.qml"),
                jobdir.glob("**/*.sld"),
                jobdir.glob("**/*.db"),
            )
        else:
            files_to_store = files

        #
        # Import published files and auxiliary files
        #
        self._storage.move_files(
            job_id,
            workdir=self._workdir,
            files=files_to_store,
        )



#
# Storage context mixin
#



class StorageContext:
    PUBLISHED_FILES = ".files"
    EXPIRE_FILE = ".job-expire"

    def __init__(self, conf: JobConfig, service_name: Optional[str] = None, with_expiration: bool = True):
       self._with_expiration = with_expiration
       self._store_url = conf.store_url
       self._workdir = conf.workdir
       if service_name:
            self.EXPIRE_FILE = f"{self.EXPIRE_FILE}-{service_name}"

    @property
    def with_expiration(self) -> bool:
        return self._with_expiration

    @classmethod
    def published_files(cls, jobdir: Path) -> Iterator[Path]:
        published = jobdir.joinpath(StorageContext.PUBLISHED_FILES)
        if published.exists():
            with published.open() as f:
                files = (n for n in (name.strip() for name in f.readlines()) if n)
                for file in files:
                    p = jobdir.joinpath(file)
                    if not p.is_file():
                        continue
                    yield p

    def store_reference_url(self, job_id: str, resource: str, public_url: Optional[str]) -> str:
        return store_reference_url(self._store_url, job_id, resource, public_url)


def store_reference_url(
    store_url: Template,
    job_id: str,
    resource: str,
    public_url: Optional[str],
) -> str:
    """Return a proper reference url for the resource"""
    return store_url.substitute(
        resource=resource,
        jobId=job_id,
        public_url=public_url or "",
    )


