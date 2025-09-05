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
from qjazz_core import logger

from .executor import (
    AsyncExecutor,
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
        executor: AsyncExecutor,
    ) -> Callable[[web.Application], AsyncGenerator[None, None]]:
        update_interval = conf.update_interval

        async def ctx(app: web.Application):
            service_names: set[str] = set()

            async def update_services() -> bool:
                nonlocal service_names
                try:
                    logger.trace("Updating services")
                    services = await executor.update_services()
                    current = set(services.keys())
                    if current != service_names:
                        service_names = current
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
                logger.debug("Starting update task with interval of %s s", update_interval)
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
    def _format(key, dests, p):
        return f"* {key:<15}{p.title:<30}{dests}"

    logger.info(
        "Availables services:\n%s",
        "\n".join(_format(k, dests, details) for k, (dests, details) in services.items()),
    )
