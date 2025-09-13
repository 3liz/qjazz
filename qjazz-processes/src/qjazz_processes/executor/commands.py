from random import randint
from typing import Sequence

from pydantic import JsonValue
from qjazz_core import logger

from ..worker.exceptions import (
    ServiceNotAvailable,
    UnreachableDestination,
)
from .protocols import ExecutorProtocol


class Commands(ExecutorProtocol):
    #
    # Control commands
    #

    def restart_pool(self, service: str, *, timeout: float = 5.0) -> JsonValue:
        """Restart worker pool"""
        return self._celery.control.pool_restart(
            destination=self._dests(service),
            reply=True,
            timeout=timeout,
        )

    def ping(self, service: str, timeout: float = 1.0) -> JsonValue:
        """Ping service workers"""
        return self._celery.control.ping(self._dests(service), timeout=timeout)

    def shutdown(self, service: str, *, reply: bool = True, timeout: float = 5.0) -> JsonValue:
        """Shutdown remote service"""
        return self._celery.control.shutdown(
            self._dests(service),
            reply=reply,
            timeout=timeout,
        )

    def command(
        self,
        name: str,
        *,
        destination: Sequence[str],
        broadcast: bool = False,
        reply: bool = True,
        **kwargs,
    ) -> JsonValue:
        """Send an inspect command to one or more service instances"""
        if not broadcast:
            # Pick a destination randomly, so that we can
            # use all availables workers
            index = randint(0, len(destination) - 1)  # nosec B311
            destination = (destination[index],)

        resp = self._celery.control.broadcast(
            name,
            destination=destination,
            reply=reply,
            **kwargs,
        )

        logger.trace("=command '%s': %s", name, resp)

        if reply and not resp:
            raise UnreachableDestination(f"{destination}")

        if not reply:
            return None

        if not broadcast:
            return next(iter(resp[0].values()))
        return dict(next(iter(r.items())) for r in resp)

    def _dests(self, service: str) -> Sequence[str]:
        dests = self.destinations(service)
        if not dests:
            raise ServiceNotAvailable(service)
        return dests
