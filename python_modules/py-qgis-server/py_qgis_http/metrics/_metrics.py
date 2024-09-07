""" Abstract class for metrics

    Metric's exporter connectors must
    implement this class.
"""

from abc import abstractmethod

from aiohttp import web
from pydantic import (
    BaseModel,
    Field,
    ImportString,
    JsonValue,
    WithJsonSchema,
)
from typing_extensions import (
    Annotated,
    Dict,
    Optional,
    Protocol,
    Type,
    runtime_checkable,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.condition import assert_postcondition
from py_qgis_contrib.core.config import ConfigBase

from ..channel import Channel


class MetricsConfig(ConfigBase):
    metrics_class: Annotated[
        ImportString,
        WithJsonSchema({'type': 'string'}),
        Field(
            default=None,
            title="Metric module",
            description=(
                "The module implementing request metrics"
            ),
        ),
    ]

    config: Dict[str, JsonValue] = Field({})


class Data(BaseModel, frozen=True):
    status: int
    service: str
    request: str
    project: Optional[str]
    memory_footprint: Optional[int]
    response_time: int
    latency: int
    cached: bool

    def dump_json(self) -> str:
        return self.model_dump_json()


class NoConfig(BaseModel):
    pass


@runtime_checkable
class Metrics(Protocol):

    Config: Type[BaseModel] = NoConfig

    @abstractmethod
    async def setup(self) -> None:
        ...

    @abstractmethod
    async def emit(self, request: web.Request, chan: Channel, data: Data):
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


def create_metrics(conf: MetricsConfig) -> Metrics:

    logger.info("Creating metrics %s", str(conf.metrics_class))

    metrics_class = conf.metrics_class
    metrics_conf = metrics_class.Config.model_validate(conf.config)

    instance = metrics_class(metrics_conf)
    assert_postcondition(
        isinstance(instance, Metrics),
        f"{instance} does not supports Metrics protocol",
    )

    return instance
