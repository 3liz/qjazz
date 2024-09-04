
from pydantic import JsonValue
from typing_extensions import (
    Dict,
    Iterator,
    Optional,
    Sequence,
    Tuple,
    cast,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.celery import Celery, CeleryConfig

from .exceptions import UnreachableDestination
from .models import WorkerPresence

PresenceDetails = WorkerPresence

ServiceDict = Dict[str, Tuple[Sequence[str], PresenceDetails]]

#
#  Services discovery
#


class _Services:

    def __init__(self, conf: CeleryConfig, *, name: Optional[str] = None):
        self._celery = Celery(name, conf)
        self._services: ServiceDict = {}
        self._last_updated = 0.

    def presences(self, destinations: Optional[Sequence[str]] = None) -> Dict[str, PresenceDetails]:
        """ Return presence info for online workers
        """
        data = self._celery.control.broadcast(
            'presence',
            reply=True,
            destination=destinations,
        )

        return {k: PresenceDetails.model_validate(v) for row in data for k, v in row.items()}

    def known_service(self, name: str) -> bool:
        """ Check if service is known in uploaded presences
        """
        return name in self._services

    @property
    def services(self) -> Iterator[PresenceDetails]:
        """ Return uploaded services presences
        """
        for _, pr in self._services.values():
            yield pr

    def get_services(self) -> ServiceDict:
        # Return services destinations (blocking)
        presences = self.presences()
        services: ServiceDict = {}
        for dest, pr in presences.items():
            dests, _ = services.setdefault(pr.service, ([], pr))
            cast(list, dests).append(dest)
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

    def command(
        self,
        name: str,
        *,
        broadcast: bool = False,
        reply: bool = True,
        destination: Sequence[str],
        **kwargs,
    ) -> JsonValue:
        """ Send an inspect command to one or more service instances """
        if not broadcast:
            destination = (destination[0],)

        resp = self._celery.control.broadcast(
            name,
            destination=destination,
            reply=reply,
            **kwargs,
        )

        logger.trace("=_command '%s': %s", name, resp)

        if reply and not resp:
            raise UnreachableDestination(f"{destination}")

        if not reply:
            return None

        if not broadcast:
            return next(iter(resp[0].values()))
        else:
            return dict(next(iter(r.items())) for r in resp)
