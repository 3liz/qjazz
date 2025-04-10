import asyncio

from dataclasses import dataclass
from functools import partial
from time import time
from typing import (
    Awaitable,
    Callable,
    Optional,
    Sequence,
)

from qjazz_contrib.core import logger

from .commands import Commands

# Reexports
from .executor import (  # noqa F401
    ExecutorBase,
    ExecutorConfig,
    JobExecute,
    JobResults,
    JobStatus,
    JsonDict,
    Link,
    PresenceDetails,
    ProcessDescription,
    ProcessFiles,
    ProcessLog,
    ProcessSummary,
    ServiceDict,
    ServiceNotAvailable,
)
from .processes import (  # noqa F401
    InputValueError,
    Processes,
    RunProcessException,
)


@dataclass
class Result:
    job_id: str
    get: Callable[[int], Awaitable[JobResults]]
    status: Callable[[], Awaitable[JobStatus]]


class AsyncExecutor(
    ExecutorBase,
    Commands,
    Processes,
):

    async def update_services(self) -> ServiceDict:
        """Update services destinations

        Collapse presence details under unique service
        name.
        """
        self._services = await asyncio.to_thread(self.get_services)
        logger.trace("=update_services %s", self._services)
        self._last_updated = time()
        return self._services

    async def describe(
        self,
        service: str,
        ident: str,
        *,
        project: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Optional[ProcessDescription]:
        """Return process description"""
        destinations = self.destinations(service)
        if not destinations:
            raise ServiceNotAvailable(service)

        return await asyncio.to_thread(
            self._describe,
            destinations,
            ident,
            project=project,
            timeout=timeout,
        )

    async def processes(self, service: str, timeout: Optional[float] = None) -> Sequence[ProcessSummary]:
        """Return process description summary"""
        destinations = self.destinations(service)
        if not destinations:
            raise ServiceNotAvailable(service)

        return await asyncio.to_thread(
            self._processes,
            destinations,
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
