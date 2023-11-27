""" Messages for communicating with the qgis server
    sub process
"""
import asyncio
import multiprocessing as mp

from dataclasses import dataclass, field
from enum import Enum, auto
from multiprocessing.connection import Connection
from pathlib import Path

from typing_extensions import (
    IO,
    Any,
    AsyncIterator,
    ClassVar,
    Dict,
    List,
    Literal,
    Optional,
    Self,
    Tuple,
    Type,
)

from py_qgis_cache import CheckoutStatus
from py_qgis_contrib.core import logger
from py_qgis_contrib.core.qgis import PluginType


@dataclass(frozen=True)
class Envelop:
    status: int
    msg: Optional[Any]


def send_reply(conn, msg: Optional[Any], status: int = 200):
    """  Send a reply in a envelope message
    """
    conn.send(Envelop(status, msg))


class MsgType(Enum):
    PING = auto()
    QUIT = auto()
    REQUEST = auto()
    OWSREQUEST = auto()
    APIREQUEST = auto()
    CHECKOUT_PROJECT = auto()
    DROP_PROJECT = auto()
    CLEAR_CACHE = auto()
    LIST_CACHE = auto()
    UPDATE_CACHE = auto()
    PROJECT_INFO = auto()
    PLUGINS = auto()
    CATALOG = auto()
    PUT_CONFIG = auto()
    GET_CONFIG = auto()
    ENV = auto()
    STATS = auto()


# Note: HTTPMethod is defined in python 3.11 via http module

class HTTPMethod(Enum):
    GET = auto()
    HEAD = auto()
    POST = auto()
    PUT = auto()
    DELETE = auto()
    CONNECT = auto()
    OPTIONS = auto()
    TRACE = auto()
    PATCH = auto()


# REQUEST

@dataclass(frozen=True)
class RequestReply:
    status_code: int
    data: bytes
    chunked: bool
    checkout_status: Optional[CheckoutStatus]
    headers: Dict[str, str] = field(default_factory=dict)
    cache_id: str = ""


@dataclass(frozen=True)
class RequestReport:
    memory: Optional[int]
    timestamp: float
    duration: float


@dataclass(frozen=True)
class OwsRequest:
    msg_id: ClassVar[MsgType] = MsgType.OWSREQUEST
    return_type: ClassVar[Type] = RequestReply
    service: str
    request: str
    target: str
    url: str
    version: Optional[str] = None
    direct: bool = False
    options: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    request_id: str = ""
    debug_report: bool = False


@dataclass(frozen=True)
class ApiRequest:
    msg_id: ClassVar[MsgType] = MsgType.APIREQUEST
    return_type: ClassVar[Type] = RequestReply
    name: str
    path: str
    method: HTTPMethod
    url: str = '/'
    data: Optional[bytes] = None
    delegate: bool = False,
    target: Optional[str] = None
    direct: bool = False
    options: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    request_id: str = ""
    debug_report: bool = False


@dataclass(frozen=True)
class Request:
    msg_id: ClassVar[MsgType] = MsgType.REQUEST
    return_type: ClassVar[Type] = RequestReply
    url: str
    method: HTTPMethod
    data: Optional[bytes]
    target: Optional[str]
    direct: bool = False
    headers: Dict[str, str] = field(default_factory=dict)
    request_id: str = ""
    debug_report: bool = False


@dataclass(frozen=True)
class Ping:
    msg_id: ClassVar[MsgType] = MsgType.PING
    return_type: ClassVar[Type] = None
    echo: Optional[str] = None

# QUIT


@dataclass(frozen=True)
class Quit:
    msg_id: ClassVar[MsgType] = MsgType.QUIT
    return_type: ClassVar[Type] = None


@dataclass(frozen=True)
class CacheInfo:
    uri: str
    status: CheckoutStatus
    in_cache: bool
    timestamp: Optional[float] = None
    name: str = ""
    storage: str = ""
    last_modified: Optional[float] = None
    saved_version: Optional[str] = None
    debug_metadata: Dict[str, int] = field(default_factory=dict)
    cache_id: str = ""

# PULL_PROJECT


@dataclass(frozen=True)
class CheckoutProject:
    msg_id: ClassVar[MsgType] = MsgType.CHECKOUT_PROJECT
    return_type: ClassVar[Type] = CacheInfo
    uri: str
    pull: Optional[bool] = False


# DROP_PROJECT

@dataclass(frozen=True)
class DropProject:
    msg_id: ClassVar[MsgType] = MsgType.DROP_PROJECT
    return_type: ClassVar[Type] = CacheInfo
    uri: str


# CLEAR_CACHE

@dataclass(frozen=True)
class ClearCache:
    msg_id: ClassVar[MsgType] = MsgType.CLEAR_CACHE
    return_type: ClassVar[Literal[None]] = None


# LIST_CACHE

@dataclass(frozen=True)
class ListCache:
    msg_id: ClassVar[MsgType] = MsgType.LIST_CACHE
    return_type: ClassVar[Type] = IO[CacheInfo]
    # Filter by status
    status_filter: Optional[CheckoutStatus] = None


# UPDATE_CACHE

@dataclass(frozen=True)
class UpdateCache:
    msg_id: ClassVar[MsgType] = MsgType.UPDATE_CACHE
    return_type: ClassVar[Type] = IO[CacheInfo]


# PLUGINS

@dataclass(frozen=True)
class PluginInfo:
    name: str
    path: Path
    plugin_type: PluginType
    metadata: Dict


@dataclass(frozen=True)
class Plugins:
    msg_id: ClassVar[MsgType] = MsgType.PLUGINS
    return_type: ClassVar[Type] = IO[PluginInfo]


# PROJECT_INFO

@dataclass(frozen=True)
class LayerInfo:
    layer_id: str
    name: str
    source: str
    crs: str
    is_valid: bool
    is_spatial: bool


@dataclass(frozen=True)
class ProjectInfo:
    status: CheckoutStatus
    uri: str
    filename: str
    crs: str
    last_modified: float
    storage: str
    has_bad_layers: bool
    layers: List[LayerInfo]
    cache_id: str = ""


@dataclass(frozen=True)
class GetProjectInfo:
    msg_id: ClassVar[MsgType] = MsgType.PROJECT_INFO
    return_type: ClassVar[Type] = ProjectInfo
    uri: str


# CONFIG

@dataclass(frozen=True)
class GetConfig:
    msg_id: ClassVar[MsgType] = MsgType.GET_CONFIG
    return_type: ClassVar[Type] = Dict


@dataclass(frozen=True)
class PutConfig:
    msg_id: ClassVar[MsgType] = MsgType.PUT_CONFIG
    return_type: ClassVar[Literal[None]] = None
    config: Optional[Dict] = None


#
# CATALOG
#

@dataclass(frozen=True)
class CatalogItem:
    uri: str
    name: str
    storage: str
    last_modified: float
    public_uri: str


@dataclass(frozen=True)
class Catalog:
    msg_id: ClassVar[MsgType] = MsgType.CATALOG
    return_type: ClassVar[Type] = IO[CatalogItem]
    location: Optional[str] = None


#
# ENV
#

@dataclass(frozen=True)
class GetEnv:
    msg_id: ClassVar[MsgType] = MsgType.ENV
    return_type: ClassVar[Type] = Dict


#
# Asynchronous Pipe connection reader
#

DEFAULT_TIMEOUT = 20


# Raised when there is an attempt
# to read a connection that would block
class WouldBlockError(Exception):
    pass


class Pipe:
    """ Wrapper for Connection object that allow reading asynchronously
    """
    @classmethod
    def new(cls) -> Tuple[Self, Connection]:
        parent, child = mp.Pipe(duplex=True)
        return cls(parent), child

    def __init__(self, conn: Connection):
        self._conn = conn
        self._data_available = asyncio.Event()
        asyncio.get_running_loop().add_reader(self._conn.fileno(), self._data_available.set)

    def write(self, obj):
        self._conn.send(obj)

    def flush(self):
        """ Pull out all remaining data from pipe
        """
        while self._conn.poll():
            _ = self._conn.recv_bytes()

    async def _poll(self, timeout: int):
        """ Asynchronous read of Pipe connection
        """
        try:
            if not self._conn.poll():
                await asyncio.wait_for(self._data_available.wait(), timeout)
                # This is blocking, but not infinitely
                # In some cases the _poll() method may return without timeout even
                # if there is no data to read.
                # We ensure that we are not going to block forever on recv().
                if not self._conn.poll(timeout):
                    logger.warning("Blocking timeout (%ds) in worker connection", timeout)
                    raise WouldBlockError()
        except asyncio.exceptions.TimeoutError:
            raise WouldBlockError() from None
        finally:
            self._data_available.clear()

    async def read(self, timeout: int = DEFAULT_TIMEOUT) -> Any:
        await self._poll(timeout)
        return self._conn.recv()

    async def read_message(self, timeout: int = DEFAULT_TIMEOUT) -> Any:
        """ Read an Envelop message
        """
        msg = await self.read(timeout)
        return msg.status, msg.msg

    async def read_bytes(self, timeout: int = DEFAULT_TIMEOUT) -> bytes:
        await self._poll(timeout)
        return self._conn.recv_bytes()

    async def stream_bytes(self, timeout: int = DEFAULT_TIMEOUT) -> AsyncIterator[bytes]:
        b = await self.read_bytes(timeout)
        while b:
            yield b
            b = await self.read_bytes(timeout)

    async def send_message(self, msg, timeout: int = DEFAULT_TIMEOUT) -> Tuple[int, Any]:
        self._conn.send(msg)
        response = await self.read(timeout)
        # Response must be an Envelop object
        return response.status, response.msg
