from typing import (
    Optional,
    Protocol,
    Sequence,
)

from pydantic import JsonValue
from qjazz_core.celery import Celery

from ..worker.models import WorkerPresence

PresenceDetails = WorkerPresence

ServiceDict = dict[str, tuple[Sequence[str], PresenceDetails]]


class ExecutorProtocol(Protocol):
    _celery: Celery
    _pending_expiration_timeout: int
    _services: ServiceDict

    @classmethod
    def get_destinations(cls, service: str, services: ServiceDict) -> Optional[Sequence[str]]: ...

    def destinations(self, service: str) -> Optional[Sequence[str]]: ...

    def command(
        self,
        name: str,
        *,
        destination: Sequence[str],
        broadcast: bool = False,
        reply: bool = True,
        **kwargs,
    ) -> JsonValue: ...
