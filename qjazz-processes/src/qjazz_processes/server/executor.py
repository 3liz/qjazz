from dataclasses import dataclass
from time import time
from typing import (
    Optional,
    Sequence,
)

from qjazz_core import logger

from ..executor.aio import (  # noqa F401
    AsyncExecutor,
    ExecutorConfig,
    InputValueError,
    JobExecute,
    JobResults,
    JobStatus,
    JsonDict,
    PresenceDetails,
    ProcessDescription,
    ProcessFiles,
    ProcessLog,
    ProcessSummary,
    RunProcessException,
    ServiceDict,
    ServiceNotAvailable,
)


@dataclass
class ProcessCache:
    timestamp: float
    processes: Sequence[ProcessSummary]

    def get(self, ident: str) -> Optional[ProcessSummary]:
        return next((p for p in self.processes if p.id_ == ident), None)


class Executor(AsyncExecutor):
    def __init__(self, conf: Optional[ExecutorConfig] = None, *, name: Optional[str] = None):
        super().__init__(conf, name=name)
        self._cache: dict[str, ProcessCache] = {}

    async def _update_processes_cache(self, service: str) -> ProcessCache:
        # Update cache
        # TODO: find a way to lock processes update for a given
        # service
        processes = await super().processes(service, timeout=5.0)
        cache = ProcessCache(timestamp=time(), processes=processes)
        self._cache[service] = cache
        return cache

    async def processes(
        self,
        service: str,
        timeout: Optional[float] = None,
    ) -> Sequence[ProcessSummary]:
        # Override the processes() method to retrieve
        # from cache lazily
        if not self.known_service(service):
            raise ServiceNotAvailable(service)

        (_, pr) = self._services[service]

        cached = self._cache.get(service)
        if not cached or cached.timestamp < pr.online_since:
            logger.debug("Retrieving processes for service '%s'", pr)
            cached = await self._update_processes_cache(service)

        return cached.processes

    async def get_process_summary(
        self,
        service: str,
        ident: str,
        update_cache: bool = True,
    ) -> Optional[ProcessSummary]:
        # Return process description from cache
        if update_cache:
            await self.processes(service, timeout=5.0)

        cached = self._cache.get(service)
        return cached.get(ident) if cached else None
