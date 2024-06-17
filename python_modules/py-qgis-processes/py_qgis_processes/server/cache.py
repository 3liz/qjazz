import asyncio
import traceback

from dataclasses import dataclass
from time import time

from typing_extensions import (
    Dict,
    Optional,
    Sequence,
)

from py_qgis_contrib.core import logger

from ..executor import (
    Executor,
    PresenceDetails,
    ProcessSummary,
)


@dataclass
class Entry:
    service: str
    data: Sequence[ProcessSummary]
    updated: float
    grace: int = 2   # Grace period


class ProcessesCache:

    def __init__(self) -> None:
        self._cache: Dict[str, Entry] = {}

    async def update(self, executor: Executor, timeout: float):
        #
        # Use grace period for cached entry
        #
        cache = self._cache
        for entry in cache.values():
            entry.grace -= 1

        self._cache = {e.service: e for e in cache.values() if e.grace > 0}

        async def _update(d: PresenceDetails):
            try:
                logger.debug("* Fetching process summaries from service %s", d.service)
                processes = await executor.processes(d.service, timeout)
                self._cache[d.service] = Entry(
                    service=d.service,
                    data=processes,
                    updated=time(),
                )
            except TimeoutError:
                logger.error("Timeout while fetching processes for service %s", d.service)
            except Exception:
                logger.error(
                    "%s: Error while fetching processes for service %s",
                    traceback.format_exc(),
                    d.service,
                )

        await asyncio.gather(*(_update(d) for d in executor.services))

    def get(self, service: str) -> Optional[Sequence[ProcessSummary]]:
        entry = self._cache.get(service)
        return entry.data if entry else None

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, service: str) -> bool:
        return service in self._cache

    def __getitem__(self, service: str) -> Sequence[ProcessSummary]:
        return self._cache[service].data
