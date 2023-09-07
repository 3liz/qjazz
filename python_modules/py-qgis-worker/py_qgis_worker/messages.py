""" Messages for communicating with the qgis server
    sub process
"""
import asyncio
import multiprocessing as mp

from multiprocessing.connection import Connection

from enum import Enum, auto
from typing_extensions import (
    ClassVar,
    Dict,
    Any,
    Optional,
    Type,
    Self,
    Tuple,
    Literal,
    IO,
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
    CHECKOUT_PROJECT = auto()
    DROP_PROJECT = auto()
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
    chunked: bool
    checkout_status: Optional[CheckoutStatus]
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
    version: Optional[str] = None
    direct: bool = False
    options: Optional[str] = None
    headers: Dict = field(default_factory=dict)


@dataclass(frozen=True)
class Request:
    msg_id: ClassVar[MsgType] = MsgType.REQUEST
    return_type: ClassVar[Type] = RequestReply
    url: str
    method: HTTPMethod
    data: bytes
    target: Optional[str]
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
    uri: str
    status: CheckoutStatus
    in_cache: bool
    name: str = ""
    storage: str = ""
    last_modified: Optional[float] = None
    saved_version: Optional[str] = None
    debug_metadata: Dict[str, int] = {}  # Safe with pydantic


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

#
# Asynchronous Pipe connection reader
#


DEFAULT_TIMEOUT = 5


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
