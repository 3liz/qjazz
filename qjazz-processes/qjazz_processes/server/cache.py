import asyncio
import traceback

from dataclasses import dataclass
from typing import (
    AsyncGenerator,
    Callable,
    Protocol,
    Sequence,
    Set,
)

from aiohttp import web

from qjazz_contrib.core import logger

from .executor import (
    Executor,
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


class CleanupConfProto(Protocol):
    @property
    def update_interval(self) -> int: ...


class ServiceCache:
    def cleanup_ctx(
        self,
        conf: CleanupConfProto,
        executor: Executor,
    ) -> Callable[[web.Application], AsyncGenerator[None, None]]:
        update_interval = conf.update_interval

        async def ctx(app: web.Application):
            async def update_services() -> bool:
                try:
                    logger.debug("Updating services")
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
                logger.debug("# Starting update task with interval of %s s", update_interval)
                interval = update_interval if ok else 2
                while True:
                    await asyncio.sleep(interval)
                    ok = await update_services()
                    if ok:
                        interval = update_interval
                        continue
                    interval = min(2 * interval, update_interval)

            # Attempt to fill the cache before handling
            # any request (needed for tests)
            ok = await update_services()

            update_task = asyncio.create_task(update_cache(ok))

            yield
            logger.debug("# Cancelling cache tasks")
            update_task.cancel()

        return ctx


def _log_services(services: ServiceDict):
    logger.info("Availables services: %s", tuple(services.keys()))

    if logger.is_enabled_for(logger.LogLevel.DEBUG):

        def _format(dests, details):
            return f"{dests}\n{details.model_dump_json(indent=4)}"

        logger.debug(
            "\n".join(_format(dests, details) for dests, details in services.values()),
        )
