import asyncio
import traceback

from dataclasses import dataclass
from time import time

from aiohttp import web
from typing_extensions import (
    AsyncGenerator,
    Callable,
    Dict,
    Optional,
    Sequence,
    Set,
)

from py_qgis_contrib.core import logger

from ..executor import (
    Executor,
    PresenceDetails,
    ProcessSummary,
    ServiceDict,
)


@dataclass
class Entry:
    service: str
    data: Sequence[ProcessSummary]
    idents: Set[str]
    updated: float
    grace: int  # Grace period


class ProcessesCache:

    def __init__(self, grace: int) -> None:
        self._grace = grace
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
                processes = await executor.processes(d.service, timeout)
                logger.debug("* Fetched %s processes from service %s", len(processes), d.service)
                self._cache[d.service] = Entry(
                    service=d.service,
                    data=processes,
                    idents=set(p.id_ for p in processes),
                    updated=time(),
                    grace=self._grace,
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

    def exists(self, service: str, ident: str) -> bool:
        entry = self._cache.get(service)
        return entry is not None and ident in entry.idents

    def get(self, service: str) -> Optional[Sequence[ProcessSummary]]:
        entry = self._cache.get(service)
        return entry.data if entry else None

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, service: str) -> bool:
        return service in self._cache

    def __getitem__(self, service: str) -> Sequence[ProcessSummary]:
        return self._cache[service].data

    def cleanup_ctx(
        self,
        update_interval: float,
        executor: Executor,
    ) -> Callable[[web.Application], AsyncGenerator[None, None]]:

        async def ctx(app: web.Application):

            # Set up update service task
            update_timeout = update_interval / 10.

            async def update_services() -> bool:
                try:
                    logger.info("Updating services")
                    services = await executor.update_services()
                    if services:
                        _log_services(services)
                        return True
                    else:
                        logger.warning("No services availables")
                except Exception:
                    logger.error("Failed to update services: %s", traceback.format_exc())

                return False

            #
            # If there was no services at startup, use incremental
            # update interval.
            # This will prevent race condition at startup when
            # both services and worker are started at the same
            # time
            #

            async def update_cache(ok: bool):
                interval = update_interval if ok else 2
                while True:
                    await asyncio.sleep(interval)
                    ok = await update_services()
                    await self.update(executor, update_timeout)
                    if ok:
                        interval = update_interval
                        continue
                    interval = min(2 * interval, update_interval)

            # Attempt to fill the cache before handling
            # any request (needed for tests
            ok = await update_services()
            if ok:
                await self.update(executor, update_timeout)

            update_task = asyncio.create_task(update_cache(ok))

            yield
            logger.debug("Cancelling update task")
            update_task.cancel()

        return ctx


def _log_services(services: ServiceDict):
    logger.info("Availables services: %s", tuple(services.keys()))

    if logger.isEnabledFor(logger.LogLevel.DEBUG):

        def _format(dests, details):
            return f"{dests}\n{details.model_dump_json(indent=4)}"

        logger.debug(
            "\n".join(
                _format(dests, details) for dests, details in services.values()
            ),
        )
