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
    WithJsonSchema,
    model_validator,
)
from typing_extensions import (
    Annotated,
    Any,
    Dict,
    Optional,
    Protocol,
    Self,
    runtime_checkable,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import ConfigBase

from ..channel import Channel


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


@runtime_checkable
class Metrics(Protocol):

    @abstractmethod
    async def setup(self) -> None:
        ...

    @abstractmethod
    async def emit(self, request: web.Request, chan: Channel, data: Data):
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class MetricsConfig(ConfigBase):
    name: Annotated[
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

    options: Dict[str, Any] = Field({})

    @model_validator(mode='after')
    def validate_options(self) -> Self:
        klass = self.name

        if not issubclass(klass, Metrics):
            raise ValueError(f"{klass} does not support Metrics protocol")

        self._metrics_options: BaseModel | None = None
        if hasattr(klass, 'Options') and issubclass(klass.Options, BaseModel):
            self._metrics_options = klass.Options.model_validate(self.options)

        return self

    def create_instance(self) -> Metrics:
        logger.info("Creating metrics %s", str(self.name))
        if self._metrics_options:
            return self.name(self._metrics_options)
        else:
            return self.name()
