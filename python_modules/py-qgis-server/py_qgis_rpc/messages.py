""" Messages for communicating with the qgis server
    sub process
"""
import asyncio
import os
import pickle  # nosec

from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from io import BytesIO
from pathlib import Path
from struct import pack, unpack

from pydantic import JsonValue
from typing_extensions import (
    Any,
    AsyncIterator,
    ClassVar,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    Type,
    Union,
)

from py_qgis_cache import CheckoutStatus
from py_qgis_contrib.core.qgis import PluginType


class MsgType(IntEnum):
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
    TEST = auto()

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


#
# REQUEST
#
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
class OwsRequestMsg:
    msg_id: ClassVar[MsgType] = MsgType.OWSREQUEST
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
class ApiRequestMsg:
    msg_id: ClassVar[MsgType] = MsgType.APIREQUEST
    name: str
    path: str
    method: HTTPMethod
    url: str = '/'
    data: Optional[bytes] = None
    delegate: bool = False
    target: Optional[str] = None
    direct: bool = False
    options: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    request_id: str = ""
    debug_report: bool = False


@dataclass(frozen=True)
class RequestMsg:
    msg_id: ClassVar[MsgType] = MsgType.REQUEST
    url: str
    method: HTTPMethod
    data: Optional[bytes]
    target: Optional[str]
    direct: bool = False
    headers: Dict[str, str] = field(default_factory=dict)
    request_id: str = ""
    debug_report: bool = False


@dataclass(frozen=True)
class PingMsg:
    msg_id: ClassVar[MsgType] = MsgType.PING
    echo: Optional[str] = None


#
# QUIT
#
@dataclass(frozen=True)
class QuitMsg:
    msg_id: ClassVar[MsgType] = MsgType.QUIT


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
    last_hit: float = 0
    hits: int = 0
    pinned: bool = False


#
# PULL_PROJECT
#
@dataclass(frozen=True)
class CheckoutProjectMsg:
    msg_id: ClassVar[MsgType] = MsgType.CHECKOUT_PROJECT
    uri: str
    pull: bool = False


#
# DROP_PROJECT
#
@dataclass(frozen=True)
class DropProjectMsg:
    msg_id: ClassVar[MsgType] = MsgType.DROP_PROJECT
    uri: str


#
# CLEAR_CACHE
#
@dataclass(frozen=True)
class ClearCacheMsg:
    msg_id: ClassVar[MsgType] = MsgType.CLEAR_CACHE


#
# LIST_CACHE
#
@dataclass(frozen=True)
class ListCacheMsg:
    msg_id: ClassVar[MsgType] = MsgType.LIST_CACHE
    # Filter by status
    status_filter: Optional[CheckoutStatus] = None


#
# UPDATE_CACHE
#
@dataclass(frozen=True)
class UpdateCacheMsg:
    msg_id: ClassVar[MsgType] = MsgType.UPDATE_CACHE


#
# PLUGINS
#
@dataclass(frozen=True)
class PluginInfo:
    name: str
    path: Path
    plugin_type: PluginType
    metadata: JsonValue


@dataclass(frozen=True)
class PluginsMsg:
    msg_id: ClassVar[MsgType] = MsgType.PLUGINS


#
# PROJECT_INFO
#
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
class GetProjectInfoMsg:
    msg_id: ClassVar[MsgType] = MsgType.PROJECT_INFO
    uri: str


#
# CONFIG
#
@dataclass(frozen=True)
class GetConfigMsg:
    msg_id: ClassVar[MsgType] = MsgType.GET_CONFIG


@dataclass(frozen=True)
class PutConfigMsg:
    msg_id: ClassVar[MsgType] = MsgType.PUT_CONFIG
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
class CatalogMsg:
    msg_id: ClassVar[MsgType] = MsgType.CATALOG
    location: Optional[str] = None


#
# ENV
#
@dataclass(frozen=True)
class GetEnvMsg:
    msg_id: ClassVar[MsgType] = MsgType.ENV


#
# TEST
#
@dataclass(frozen=True)
class TestMsg:
    msg_id: ClassVar[MsgType] = MsgType.TEST
    delay: int

#
# Asynchronous Pipe connection reader
#


@dataclass(frozen=True)
class Envelop:
    status: int
    msg: Any


Message = Union[
    OwsRequestMsg,
    ApiRequestMsg,
    RequestMsg,
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
    TestMsg,
]


class Connection(Protocol):
    def recv(self) -> Message: ...
    def send_bytes(self, data: bytes): ...


def send_reply(conn: Connection, msg: Any, status: int = 200):  # noqa ANN401
    """  Send a reply in a envelope message """
    conn.send_bytes(pickle.dumps(Envelop(status, msg=msg)))


def send_report(conn: Connection, report: RequestReport):
    """ Send report """
    conn.send_bytes(pickle.dumps(report))


#
# XXX Note that data sent by child *MUST* be retrieved in parent
# side, otherwise cpu goes wild.


def cast_into[T](o: Any, t: Type[T]) -> T:  # noqa ANN401
    if not isinstance(o, t):
        raise ValueError(f"Cast failed, Expecting {t}, not {type(o)}")
    return o


class Pipe:
    """ Wrapper for Connection object that allow reading asynchronously
    """
    def __init__(self, proc: asyncio.subprocess.Process):
        if proc.stdin is None:
            raise ValueError("Invalid StreamWriter")
        if proc.stdout is None:
            raise ValueError("Invalid StreamReader")
        self._stdin = proc.stdin
        self._stdout = proc.stdout

    async def put_message(self, message: Message):
        data = pickle.dumps(message)
        self._stdin.write(pack('i', len(data)))
        self._stdin.write(data)
        await self._stdin.drain()

    async def drain(self):
        """ Pull out all remaining data from pipe
        """
        size = unpack('i', await self._stdout.readexactly(4))
        if size > 0:
            _ = await self._stdout.read(size)

    async def read_report(self) -> RequestReport:
        return cast_into(
            pickle.loads(await self.read_bytes()),  # nosec
            RequestReport,
        )

    async def read_message(self) -> Tuple[int, Any]:
        """ Read an Envelop message
        """
        msg = cast_into(
            pickle.loads(await self.read_bytes()),  # nosec
            Envelop,
        )

        return msg.status, msg.msg

    async def read_bytes(self) -> bytes:
        size, = unpack('i', await self._stdout.read(4))
        data = await self._stdout.read(size) if size else b''
        if len(data) < size:
            buf = BytesIO()
            buf.write(data)
            remaining = size - len(data)
            while remaining > 0:
                chunk = await self._stdout.read(remaining)
                remaining -= len(chunk)
                buf.write(chunk)
            data = buf.getvalue()
        return data

    async def stream_bytes(self) -> AsyncIterator[bytes]:
        b = await self.read_bytes()
        while b:
            yield b
            b = await self.read_bytes()

    async def send_message(self, msg: Message) -> Tuple[int, Any]:
        await self.put_message(msg)
        return await self.read_message()

#
# Rendez Vous
#


class RendezVous:

    def __init__(self, path: Path):
        self._path = path
        self._done = asyncio.Event()
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def path(self) -> Path:
        return self._path

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    def start(self):
        if self._task:
            raise RuntimeError("Rendez vous already started")
        self._task = asyncio.create_task(self._listen())

    @property
    def done(self) -> bool:
        return self._done.is_set()

    @property
    def busy(self) -> bool:
        return not self.done

    async def wait(self):
        await self._done.wait()

    async def _listen(self):
        # Open a named pipe and read continuously from it.
        #
        #    Writer just need to open the path
        #    in binary write mode (rb)
        #
        #    ```
        #    rendez_vous = path.open('wb')
        #    ```
        self._running = True

        path = self.path.as_posix()
        os.mkfifo(path)
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        avail = asyncio.Event()
        asyncio.get_running_loop().add_reader(fd, avail.set)
        while self._running:
            await avail.wait()
            try:
                match os.read(fd, 1024):
                    case b'0':  # DONE
                        self._done.set()
                    case b'1':  # BUSY
                        self._done.clear()
            except BlockingIOError:
                pass
            avail.clear()
