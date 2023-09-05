""" Messages for communicating with the qgis server
    sub process
"""
import asyncio
import multiprocessing as mp

from enum import Enum, auto
from typing_extensions import (
    ClassVar,
    Dict,
    Any,
    Optional,
    Type,
    List,
    Self,
    Tuple,
    Literal,
    AsyncIterator,
)
from dataclasses import dataclass, field
from pydantic import BaseModel

from py_qgis_project_cache import CheckoutStatus


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
    PULL_PROJECT = auto()
    UNLOAD_PROJECT = auto()
    CLEAR_CACHE = auto()
    LIST_CACHE = auto()
    PROJECT_INFO = auto()
    LIST_PLUGINS = auto()


# Note: This is defined in python 3.11 via http module
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
    checkout_status: CheckoutStatus
    chunked: bool
    headers: Dict = field(default_factory=dict)


@dataclass(frozen=True)
class RequestReport:
    memory: Optional[int]
    timestamp: float
    duration: float


@dataclass(frozen=True)
class OWSRequest:
    msg_id: ClassVar[MsgType] = MsgType.OWSREQUEST
    return_type: ClassVar[Type] = RequestReply
    service: str
    request: str
    target: str
    url: str
    direct: bool = False
    options: Dict[str, str] = field(default_factory=dict)
    headers: Dict = field(default_factory=dict)


@dataclass(frozen=True)
class Request:
    msg_id: ClassVar[MsgType] = MsgType.REQUEST
    return_type: ClassVar[Type] = RequestReply
    data: bytes
    target: Optional[str]
    url: str
    method: HTTPMethod
    direct: bool = False
    headers: Dict = field(default_factory=dict)


@dataclass(frozen=True)
class Ping:
    msg_id: ClassVar[MsgType] = MsgType.PING
    return_type: ClassVar[Type] = None


# QUIT


@dataclass(frozen=True)
class Quit:
    msg_id: ClassVar[MsgType] = MsgType.QUIT
    return_type: ClassVar[Type] = None


class CacheInfo(BaseModel, frozen=True):
    url: str
    last_modified: Optional[int]
    saved_version: Optional[int]
    status: CheckoutStatus


# PULL_PROJECT

@dataclass(frozen=True)
class PullProject:
    msg_id: ClassVar[MsgType] = MsgType.PULL_PROJECT
    return_type: ClassVar[Type] = CacheInfo
    uri: str

# UNLOAD_PROJECT


@dataclass(frozen=True)
class UnloadProject:
    msg_id: ClassVar[MsgType] = MsgType.UNLOAD_PROJECT
    return_type: ClassVar[Type] = CacheInfo
    uri: str

# CLEAR_CACHE


@dataclass(frozen=True)
class ClearCache:
    msg_id: ClassVar[MsgType] = MsgType.CLEAR_CACHE
    return_type: ClassVar[Literal[None]] = None

# LIST_CACHE


class CacheList(BaseModel, frozen=True):
    cached: List[CacheInfo]


# LIST_CACHE
@dataclass(frozen=True)
class ListCache:
    msg_id: ClassVar[MsgType] = MsgType.LIST_CACHE
    return_type: ClassVar[Type] = CacheList
    # Filter by status
    status: Optional[CheckoutStatus] = None

#
# Asynchronous Pipe connection reader
#


DEFAULT_TIMEOUT = 5


class Pipe:
    """ Wrapper for Connection object that allow reading asynchronously
    """
    @classmethod
    def new(cls) -> Tuple[Self, mp.connection.Connection]:
        parent, child = mp.Pipe(duplex=True)
        return cls(parent), child

    def __init__(self, conn: mp.connection.Connection):
        self._conn = conn
        self._data_available = asyncio.Event()
        asyncio.get_event_loop().add_reader(self._conn.fileno(), self._data_available.set)

    def write(self, obj):
        self._conn.send(obj)

    async def _poll(self, timeout: int):
        """ Asynchronous read of Pipe connection
        """
        try:
            if not self._conn.poll():
                await asyncio.wait_for(self._data_available.wait(), timeout)
        finally:
            self._data_available.clear()

    async def read(self, timeout: int = DEFAULT_TIMEOUT) -> Any:
        await self._poll(timeout)
        return self._conn.recv()

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
        assert isinstance(response, Envelop)
        return response.status, response.msg
