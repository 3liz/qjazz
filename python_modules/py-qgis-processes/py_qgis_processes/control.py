
from time import time

import celery

from pydantic import JsonValue
from typing_extensions import (
    Dict,
    Iterator,
    Optional,
    Sequence,
)

from .exceptions import ServiceNotAvailable
from .services import (
    CeleryConfig,
    PresenceDetails,
    ServiceDict,
    _Services,
)


class Control:

    def __init__(self, conf: CeleryConfig):
        self._base = _Services(conf)

    def presences(self, destinations: Optional[Sequence[str]] = None) -> Dict[str, PresenceDetails]:
        return self._base.presences(destinations)

    def known_service(self, name: str) -> bool:
        return self._base.known_service(name)

    @property
    def services(self) -> Iterator[PresenceDetails]:
        yield from self._base.services

    def get_services(self) -> ServiceDict:
        self._base._services = self._base.get_services()
        self._last_updated = time()
        return self._base._services

    @property
    def last_updated(self) -> float:
        return self._base.last_updated

    def destinations(self, service: str, raise_exc: bool = False) -> Optional[Sequence[str]]:
        dests = self._base.destinations(service)
        if raise_exc and not dests:
            raise ServiceNotAvailable(service)
        return dests

    @property
    def control(self) -> celery.app.control.Control:
        return self._base._celery.control

    # Inspect
    def inspect(self, service: Optional[str] = None) -> celery.app.control.Inspect:
        return self._base._celery.inspect(
            destination=service and self.destinations(service, True),
        )

    # Control commands

    def restart_pool(self, service: str, *, reply: bool = True) -> JsonValue:
        """ Restart worker pool
        """
        return self.control.pool_restart(destination=self.destinations(service, True), reply=reply)

    def ping(self, service: str, timeout: float = 1.) -> JsonValue:
        """ Ping service workers
        """
        return self.control.ping(self.destinations(service, True), timeout=timeout)

    def shutdown(self, service: str, **kwargs) -> JsonValue:
        return self.control.shutdown(self.destinations(service, True), **kwargs)
