from pydantic import (  # noqa
    BaseModel,
    Field,
    Json,
    TypeAdapter,
    ValidationError,
    WithJsonSchema,
)
from typing import (
    Annotated,
    Literal,
    Optional,
    Self,
)

from qjazz_core.models import (
    JsonModel,
)

from . import swagger
from .pool import PoolClient

AnyJson = Annotated[
    Json,
    WithJsonSchema({"type": "object"}),
]


@swagger.model
class ErrorResponse(JsonModel):
    message: str
    details: Optional[AnyJson] = None


@swagger.model
class BackendStatus(JsonModel):
    """Pool backend status"""

    address: str
    numWorkers: Optional[int] = None
    request_pressure: Optional[float] = None
    status: Literal["ok", "unavailable"]
    stopped_workers: Optional[int] = None
    worker_failure_pressure: Optional[float] = None
    uptime: Optional[int] = None


@swagger.model
class PoolBackendsResponse(JsonModel):
    label: str
    address: str
    backends: list[BackendStatus]


@swagger.model
class PoolInfos(JsonModel):
    label: str
    address: str
    backends: list[str]
    title: str
    description: Optional[str]

    links: list[swagger.Link]

    @classmethod
    def _from_pool(cls: type[Self], pool: PoolClient, links: list[swagger.Link]) -> Self:
        return cls(
            label=pool.label,
            address=pool.address,
            backends=[be.address for be in pool.backends],
            title=pool.title,
            description=pool.description,
            links=links,
        )


PoolListResponse = swagger.model(
    TypeAdapter(list[PoolInfos]),
    name="PoolListResponse",
)


@swagger.model
class PoolBackendConfig(JsonModel):
    label: str
    address: str
    config: AnyJson
    env: AnyJson


@swagger.model
class PoolSetConfigResponse(JsonModel):
    label: str
    address: str
    diff: AnyJson


class JsonValidator(BaseModel):
    """A validator for json input body"""

    body: AnyJson


#
#  Cache
#


@swagger.model
class CacheItem(JsonModel):
    in_cache: bool
    last_modified: Annotated[
        str,
        WithJsonSchema(
            {
                "type": "string",
                "format": "date-time",
            }
        ),
    ]
    name: str
    saved_version: str
    status: str
    storage: str
    uri: str
    debug_metadata: Optional[dict[str, str]]
    timestamp: int
    last_hit: int
    hits: int


@swagger.model
class CacheItemPool(JsonModel):
    pool: dict[str, CacheItem]
    links: list[swagger.Link]


StringList = swagger.model(
    TypeAdapter(list[str]),
    name="StringList",
)
