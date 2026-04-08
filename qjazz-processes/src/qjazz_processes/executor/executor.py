import asyncio

from dataclasses import dataclass
from functools import partial
from time import time
from typing import (
    Awaitable,
    Callable,
    Iterator,
    Optional,
    Sequence,
    cast,
)

from qjazz_core import logger
from qjazz_core.celery import Celery, CeleryConfig
from qjazz_core.config import ConfigBase
from qjazz_core.models import Field

from ..schemas import (
    JobExecute,
    JobResults,
    JobStatus,
    JsonDict,
    ProcessDescription,
    ProcessSummary,
)
from ..worker.exceptions import ServiceNotAvailable
from ..worker.models import Link, ProcessFiles, ProcessLog
from .commands import Commands
from .processes import Processes
from .protocols import PresenceDetails, ServiceDict


class ExecutorConfig(ConfigBase):
    celery: CeleryConfig = CeleryConfig()

    message_expiration_timeout: int = Field(
        default=600,
        title="Message expiration timeout",
        description="""
        The amount of time an execution message
        can wait on queue before beeing processed
        with asynchronous response.
        """,
    )


class ExecutorBase(Commands, Processes):
    def __init__(
        self,
        conf: Optional[ExecutorConfig] = None,
        *,
        name: Optional[str] = None,
    ):
        conf = conf or ExecutorConfig()
        self._celery = Celery(name, conf.celery)
        self._services: ServiceDict = {}
        self._pending_expiration_timeout = conf.message_expiration_timeout
        self._last_updated = 0.0

    def presences(
        self,
        destinations: Optional[Sequence[str]] = None,
    ) -> dict[str, PresenceDetails]:
        """Return presence info for online workers"""
        data = self._celery.control.broadcast(
            "presence",
            reply=True,
            destination=destinations,
        )

        return {k: PresenceDetails.model_validate(v) for row in data for k, v in row.items()}

    def known_service(self, name: str) -> bool:
        """Check if service is known in uploaded presences"""
        return name in self._services

    @property
    def services(self) -> Iterator[PresenceDetails]:
        """Return uploaded services presences"""
        for _, pr in self._services.values():
            yield pr

    @property
    def num_services(self) -> int:
        return len(self._services)

    def get_services(self) -> ServiceDict:
        """Return services destinations (blocking)

        Collapse presence details under unique
        service name.
        """
        presences = self.presences()
        services: ServiceDict = {}
        for dest, pr in presences.items():
            dests, _ = services.setdefault(pr.service, ([], pr))
            cast("list", dests).append(dest)
        return {k: (tuple(dests), pr) for k, (dests, pr) in services.items()}

    @property
    def last_updated(self) -> float:
        return self._last_updated

    @classmethod
    def get_destinations(cls, service: str, services: ServiceDict) -> Optional[Sequence[str]]:
        item = services.get(service)
        return item and item[0]

    def destinations(self, service: str) -> Optional[Sequence[str]]:
        return self.get_destinations(service, self._services)

    def ensure_destinations(self, service: str) -> Sequence[str]:
        destinations = self.destinations(service)
        if not destinations:
            raise ServiceNotAvailable(service)
        return destinations

    def _update_services(self, services: ServiceDict) -> ServiceDict:
        """Update service destinations
        """
        self._services = services
        logger.trace("=update_services %s", self._services)
        self._last_updated = time()
        return self._services


# =====================
# Async Executor
# =====================

@dataclass
class Result:
    job_id: str
    get: Callable[[int], Awaitable[JobResults]]
    status: Callable[[], Awaitable[JobStatus]]


class AsyncExecutor(ExecutorBase):
    async def update_services(self) -> ServiceDict:
        """Update services destinations"""
        return self._update_services(
            await asyncio.to_thread(self.get_services),
        )

    async def describe(
        self,
        service: str,
        ident: str,
        *,
        project: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Optional[ProcessDescription]:
        """Return process description"""
        return await asyncio.to_thread(
            self._describe,
            self.ensure_destinations(service),
            ident,
            project=project,
            timeout=timeout,
        )

    async def processes(self, service: str, timeout: Optional[float] = None) -> Sequence[ProcessSummary]:
        """Return process description summary"""
        return await asyncio.to_thread(
            self._processes,
            self.ensure_destinations(service),
            timeout,
        )

    def execute(
        self,
        service: str,
        ident: str,
        request: JobExecute,
        *,
        project: Optional[str] = None,
        context: Optional[JsonDict] = None,
        realm: Optional[str] = None,
        pending_timeout: Optional[int] = None,
        tag: Optional[str] = None,
        countdown: Optional[int] = None,
        priority: int = 0,
    ) -> Result:
        """Send an execute request
        Returns an asynchronous  'Result' object
        """
        job_id, _get_result, _get_status = self._execute(
            service,
            ident,
            request,
            project=project,
            context=context,
            realm=realm,
            pending_timeout=pending_timeout,
            tag=tag,
            countdown=countdown,
            priority=priority,
        )

        return Result(
            job_id=job_id,
            get=partial(asyncio.to_thread, _get_result),  # type: ignore [call-arg]
            status=partial(asyncio.to_thread, _get_status),
        )

    async def dismiss(
        self,
        job_id: str,
        *,
        realm: Optional[str] = None,
        timeout: int = 20,
    ) -> Optional[JobStatus]:
        """Delete job"""
        return await asyncio.to_thread(
            self._dismiss,
            job_id,
            self._services,
            realm=realm,
            timeout=timeout,
        )

    async def job_status(
        self,
        job_id: str,
        *,
        realm: Optional[str] = None,
        with_details: bool = False,
    ) -> Optional[JobStatus]:
        """Return job status"""
        return await asyncio.to_thread(
            self._job_status_ext,
            job_id,
            self._services,
            realm,
            with_details,
        )

    async def job_results(
        self,
        job_id: str,
        *,
        realm: Optional[str] = None,
    ) -> Optional[JobResults]:
        """Return job results"""
        return await asyncio.to_thread(self._job_results, job_id, realm=realm)

    async def jobs(
        self,
        service: Optional[str] = None,
        *,
        realm: Optional[str] = None,
        cursor: int = 0,
        limit: int = 100,
    ) -> Sequence[JobStatus]:
        """Iterate over job statuses"""
        return await asyncio.to_thread(
            self._jobs,
            self._services,
            service=service,
            realm=realm,
            cursor=cursor,
            limit=limit,
        )

    async def log_details(
        self,
        job_id: str,
        *,
        realm: Optional[str] = None,
        timeout: int = 20,
    ) -> Optional[ProcessLog]:
        """Return process execution logs"""
        return await asyncio.to_thread(
            self._log_details,
            job_id,
            self._services,
            realm=realm,
            timeout=timeout,
        )

    async def files(
        self,
        job_id: str,
        *,
        public_url: Optional[str] = None,
        realm: Optional[str] = None,
        timeout: int = 20,
    ) -> Optional[ProcessFiles]:
        """Return process execution files"""
        return await asyncio.to_thread(
            self._files,
            job_id,
            self._services,
            public_url=public_url,
            realm=realm,
            timeout=timeout,
        )

    async def download_url(
        self,
        job_id: str,
        *,
        resource: str,
        timeout: int,
        expiration: int,
        realm: Optional[str] = None,
    ) -> Optional[Link]:
        """Return download url"""
        return await asyncio.to_thread(
            self._download_url,
            job_id,
            self._services,
            resource=resource,
            expiration=expiration,
            timeout=timeout,
            realm=realm,
        )

