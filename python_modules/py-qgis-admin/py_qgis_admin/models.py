
from pydantic import (  # noqa
    BaseModel,
    Field,
    Json,
    TypeAdapter,
    ValidationError,
    WithJsonSchema,
)

from typing_extensions import (  # noqa
    Annotated,
    Literal,
    Optional,
    List,
    Set,
    Dict,
    Self,
    Type,
)


from . import swagger
from .pool import PoolClient


AnyJson = Annotated[
    Json,
    WithJsonSchema({'type': 'object'})
]


@swagger.model
class ErrorResponse(BaseModel):
    message: str
    details: Optional[AnyJson] = None


@swagger.model
class BackendStatus(BaseModel):
    """ Pool backend status
    """
    address: str
    numWorkers: Optional[int] = None
    requestPressure: Optional[float] = None
    status: Literal["ok", "unavailable"]
    stoppedWorkers: Optional[int] = None
    workerFailurePressure: Optional[float] = None
    uptime: Optional[int] = None


@swagger.model
class PoolBackendsResponse(BaseModel):
    label: str
    address: str
    backends: List[BackendStatus]


@swagger.model
class PoolInfos(BaseModel):
    label: str
    address: str
    backends: List[str]
    links: List[swagger.Link]

    @classmethod
    def _from_pool(cls, pool: PoolClient, links: List[swagger.Link]) -> Self:
        return cls(
            label=pool.label,
            address=pool.address,
            backends=[be.address for be in pool.backends],
            links=links,
        )


PoolListResponse = swagger.model(
    TypeAdapter(List[PoolInfos]),
    name="PoolListResponse",
)


@swagger.model
class PoolBackendConfig(BaseModel):
    label: str
    address: str
    config: AnyJson
    env: AnyJson


@swagger.model
class PoolSetConfigResponse(BaseModel):
    label: str
    address: str
    diff: AnyJson


class JsonValidator(BaseModel):
    """ A validator for json input body
    """
    body: AnyJson


#
#  Cache
#


@swagger.model
class CacheItem(BaseModel):
    inCache: bool
    lastModified: Annotated[
        str,
        WithJsonSchema({
            "type": "string",
            "format": "date-time",
        })
    ]
    name: str
    savedVersion: str
    status: str
    storage: str
    uri: str
    debugMetadata: Optional[Dict[str, str]]


@swagger.model
class CacheItemPool(BaseModel):
    pool: Dict[str, CacheItem]
    links: List[swagger.Link] = []


StringList = swagger.model(
    TypeAdapter(List[str]),
    name="StringList",
)
