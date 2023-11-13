""" Abstract class for metrics

    Metric's exporter connectors must
    implement this class.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing_extensions import Self

METRICS_HANDLER_ENTRYPOINTS = '3liz.org.metrics.handler.1'
METRICS_HANDLER_CONTRACTID = '@3liz.org/metrics/handler;1'


@dataclass(frozen=True)
class Data:
    status: int
    service: str
    request: str
    project: str
    memory_footprint: int
    response_time: int
    cached: bool


class Metrics(ABC):

    @abstractmethod
    def initialize(**options) -> Self:
        ...

    @abstractmethod
    def emit(self, key: str, data: Data) -> None:
        ...


def get_service(name: str):
    """ Return registered handler
    """
    from py_qgis_contrib.core import componentmanager as cm
    return cm.get_service(f"{METRICS_HANDLER_CONTRACTID}?name={name}")


def load_service(name: str):
    """ Load entrypoint for metrics handler given by 'name'
    """
    from py_qgis_contrib.core import componentmanager as cm
    cm.load_entrypoint(METRICS_HANDLER_ENTRYPOINTS, name)
