"""Messages for communicating with the qgis server
sub process
"""

from enum import IntEnum, StrEnum
from typing import (
    Annotated,
    Any,
    ByteString,
    Iterable,
    Literal,
    NewType,
    Optional,
    Protocol,
    Union,
)

from msgpack import packb
from pydantic import BaseModel, Field, JsonValue, TypeAdapter

from qjazz_cache.status import CheckoutStatus


class MsgType(IntEnum):
    PING = 1
    QUIT = 2
    # REQUEST = 3
    OWSREQUEST = 4
    APIREQUEST = 5
    CHECKOUT_PROJECT = 6
    DROP_PROJECT = 7
    CLEAR_CACHE = 8
    LIST_CACHE = 9
    UPDATE_CACHE = 10
    PROJECT_INFO = 11
    PLUGINS = 12
    CATALOG = 13
    PUT_CONFIG = 14
    GET_CONFIG = 15
    ENV = 16
    STATS = 17
    SLEEP = 18
    COLLECTIONS = 19


# Note: HTTPMethod is defined in python 3.11 via http module


class HTTPMethod(StrEnum):
    GET = "GET"
    HEAD = "HEAD"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELATE"
    CONNECT = "CONNECT"
    OPTIONS = "OPTIONS"
    TRACE = "TRACE"
    PATCH = "PATCH"


class MsgModel(BaseModel, frozen=True):
    pass


class Response(BaseModel):
    def dump_response(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)


#
# REQUEST
#
class RequestReply(Response):
    status_code: int
    target: Optional[str]
    checkout_status: Optional[int]
    headers: list[tuple[str, str]] = Field([])
    cache_id: str = ""


# OWS
#
class OwsRequestMsg(MsgModel):
    msg_id: Literal[MsgType.OWSREQUEST] = MsgType.OWSREQUEST
    service: str
    request: str
    target: str
    url: Optional[str]
    version: Optional[str] = None
    direct: bool = False
    options: Optional[str] = None
    headers: list[tuple[str, str]] = Field([])
    request_id: Optional[str] = None
    header_prefix: Optional[str] = None
    content_type: Optional[str] = None
    method: Optional[HTTPMethod] = None
    body: Optional[bytes] = None
    send_report: bool = False


#
# API
#
class ApiRequestMsg(MsgModel):
    msg_id: Literal[MsgType.APIREQUEST] = MsgType.APIREQUEST
    name: str
    path: str
    method: HTTPMethod
    url: str = "/"
    data: Optional[bytes] = None
    delegate: bool = False
    target: Optional[str] = None
    direct: bool = False
    options: Optional[str] = None
    headers: list[tuple[str, str]] = Field([])
    request_id: Optional[str] = None
    header_prefix: Optional[str] = None
    content_type: Optional[str] = None
    send_report: bool = False


#
# Collections
#


class CollectionsMsg(MsgModel):
    msg_id: Literal[MsgType.COLLECTIONS] = MsgType.COLLECTIONS
    location: Optional[str] = None
    resource: Optional[str] = None
    start: int = 0
    end: int = 50


class CollectionsItem(Response):
    name: str
    json_: str | bytes = Field(alias="json")
    endpoints: int  # qjazz_ogc.OgcEndpoints


class CollectionsPage(Response):
    schema_: str = Field(alias="schema")
    next: bool
    items: list[CollectionsItem]


#
# Ping
#
class PingMsg(MsgModel):
    msg_id: Literal[MsgType.PING] = MsgType.PING
    echo: Optional[str] = None


#
# QUIT
#
class QuitMsg(MsgModel):
    msg_id: Literal[MsgType.QUIT] = MsgType.QUIT


class CacheInfo(Response):
    uri: str
    status: int  # CheckoutStatus
    in_cache: bool
    cache_id: str
    timestamp: Optional[int] = None
    name: Optional[str] = None
    storage: Optional[str] = None
    last_modified: Optional[str] = None
    saved_version: Optional[str] = None
    debug_metadata: dict[str, int] = Field({})
    last_hit: int = 0
    hits: int = 0
    pinned: bool = False


#
# PULL_PROJECT
#
class CheckoutProjectMsg(MsgModel):
    msg_id: Literal[MsgType.CHECKOUT_PROJECT] = MsgType.CHECKOUT_PROJECT
    uri: str
    pull: bool = False


#
# DROP_PROJECT
#
class DropProjectMsg(MsgModel):
    msg_id: Literal[MsgType.DROP_PROJECT] = MsgType.DROP_PROJECT
    uri: str


#
# CLEAR_CACHE
#
class ClearCacheMsg(MsgModel):
    msg_id: Literal[MsgType.CLEAR_CACHE] = MsgType.CLEAR_CACHE


#
# LIST_CACHE
#
class ListCacheMsg(MsgModel):
    msg_id: Literal[MsgType.LIST_CACHE] = MsgType.LIST_CACHE
    # Filter by status
    status_filter: Optional[CheckoutStatus] = None


#
# UPDATE_CACHE
#
class UpdateCacheMsg(MsgModel):
    msg_id: Literal[MsgType.UPDATE_CACHE] = MsgType.UPDATE_CACHE


#
# PLUGINS
#
class PluginInfo(Response):
    name: str
    path: str
    plugin_type: str
    metadata: JsonValue


class PluginsMsg(MsgModel):
    msg_id: Literal[MsgType.PLUGINS] = MsgType.PLUGINS


#
# PROJECT_INFO
#
class LayerInfo(Response):
    layer_id: str
    name: str
    source: str
    crs: str
    is_valid: bool
    is_spatial: bool


class ProjectInfo(Response):
    status: int  # CheckoutStatus
    uri: str
    filename: str
    crs: str
    last_modified: str
    storage: Optional[str]
    has_bad_layers: bool
    layers: list[LayerInfo]
    cache_id: str = ""


class GetProjectInfoMsg(MsgModel):
    msg_id: Literal[MsgType.PROJECT_INFO] = MsgType.PROJECT_INFO
    uri: str


#
# CONFIG
#
class GetConfigMsg(MsgModel):
    msg_id: Literal[MsgType.GET_CONFIG] = MsgType.GET_CONFIG


class PutConfigMsg(MsgModel):
    msg_id: Literal[MsgType.PUT_CONFIG] = MsgType.PUT_CONFIG
    config: Optional[dict | str] = None


#
# CATALOG
#
class CatalogItem(Response):
    uri: str
    name: str
    storage: str
    last_modified: str
    public_uri: str


class CatalogMsg(MsgModel):
    msg_id: Literal[MsgType.CATALOG] = MsgType.CATALOG
    location: Optional[str] = None


#
# ENV
#
class GetEnvMsg(MsgModel):
    msg_id: Literal[MsgType.ENV] = MsgType.ENV


#
# TEST
#
class SleepMsg(MsgModel):
    msg_id: Literal[MsgType.SLEEP] = MsgType.SLEEP
    delay: int


#
# Asynchronous Pipe connection reader
#


Message = Annotated[
    Union[
        OwsRequestMsg,
        ApiRequestMsg,
        CollectionsMsg,
        PingMsg,
        QuitMsg,
        CheckoutProjectMsg,
        DropProjectMsg,
        ClearCacheMsg,
        ListCacheMsg,
        UpdateCacheMsg,
        PluginsMsg,
        GetProjectInfoMsg,
        GetConfigMsg,
        PutConfigMsg,
        CatalogMsg,
        GetEnvMsg,
        SleepMsg,
    ],
    Field(discriminator="msg_id"),
]


MessageAdapter: TypeAdapter[Message] = TypeAdapter(Message)


Envelop = NewType("Envelop", tuple[int, Any])


class Connection(Protocol):
    def recv(self) -> Message: ...
    def send_bytes(self, data: ByteString): ...

    @property
    def cancelled(self) -> bool: ...


def send_reply(conn: Connection, msg: Any, status: int = 200):  # noqa ANN401
    """Send a reply in a envelope message"""
    if isinstance(msg, Response):
        msg = msg.dump_response()
    conn.send_bytes(packb((status, msg)))


# Send a binary chunk
def send_chunk(conn: Connection, data: ByteString):
    if len(data) > 0:
        conn.send_bytes(packb(206))
        conn.send_bytes(data)
    else:
        conn.send_bytes(packb(204))


def stream_data(conn: Connection, stream: Iterable):
    for item in stream:
        if isinstance(item, Response):
            item = item.dump_response()
        conn.send_bytes(packb((206, item)))
    # EOT
    conn.send_bytes(packb(204))


def send_nodata(conn: Connection):
    conn.send_bytes(packb(204))


#
# XXX Note that data sent by child *MUST* be retrieved in parent
# side, otherwise cpu goes wild.


def cast_into[T](o: Any, t: type[T]) -> T:  # noqa ANN401
    if not isinstance(o, t):
        raise ValueError(f"Cast failed, Expecting {t}, not {type(o)}")
    return o
