""" Send metrics through amqp messages
"""
from ..metrics import (
    Metrics,
    Data,
    METRICS_HANDLER_CONTRACTID,
)

from typing_extensions import Self


class AmqpMetrics(Metrics):

    def __init__(self):
        ...

    def initialize(self, **options) -> Self:
        return self

    def emit(self, key: str, data: Data) -> None:
        ...


# Entry point registration
def register(cm):
    cm.register_service(
        f"{METRICS_HANDLER_CONTRACTID}?name=amqp",
        AmqpMetrics(),
    )
