import asyncio

from contextlib import asynccontextmanager
from fnmatch import fnmatch

import grpc

from aiohttp import web
from grpc_health.v1 import (
    health_pb2,  # HealthCheckRequest
    health_pb2_grpc,  # HealthStub
)
from typing_extensions import (
    Callable,
    Iterable,
    Iterator,
    Literal,
    Optional,
    Sequence,
    Tuple,
)

from py_qgis_contrib.core import logger
from py_qgis_rpc._grpc import api_pb2, api_pb2_grpc  # noqa

from .resolver import ApiEndpoint, BackendConfig

CHANNEL_OPTIONS = [
    ("grpc.lb_policy_name", "round_robin"),
    ("grpc.enable_retries", 1),
    ("grpc.keepalive_timeout_ms", 10000),
]

BACKOFF_TIME = 5

ChannelStatus = Literal["notset", "available", "unavailable"]


class Channel:
    """ A gRPC channel reconnect itself if a backend
        so we don't need to handle a reconnection task
    """

    def __init__(self, name: str, conf: BackendConfig):
        self._name = name
        self._conf = conf
        self._channel = None
        self._connected = False
        self._serving = False
        self._health_check: Optional[asyncio.Task] = None
        self._address = conf.to_string()
        self._use_ssl = conf.use_ssl
        self._usecount = 0
        self._closing = False
        self._status: ChannelStatus = "notset"

        self._posix_route = self._conf.route.as_posix()

        def _read_if(f):
            if f:
                with f.open('rb') as fp:
                    return fp.read()

        self._ssl_creds = grpc.ssl_channel_credentials(
            root_certificates=_read_if(conf.ssl.cafile),
            certificate_chain=_read_if(conf.ssl.certfile),
            private_key=_read_if(conf.ssl.keyfile),
        ) if self._use_ssl else None

    @property
    def config(self) -> BackendConfig:
        return self._conf

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> ChannelStatus:
        return self._status

    @property
    def serving(self) -> bool:
        return self._serving

    @property
    def in_use(self) -> bool:
        return self._usecount > 0

    @property
    def address(self) -> str:
        return self._address

    @property
    def getfeature_limit(self) -> Optional[int]:
        return self._conf.getfeature_limit

    @property
    def allow_direct_resolution(self) -> bool:
        return self._conf.allow_direct_resolution

    @property
    def timeout(self) -> int:
        return self._conf.timeout

    @property
    def route(self) -> str:
        return self._posix_route

    @property
    def api_endpoints(self) -> Iterator[ApiEndpoint]:
        for ep in self._conf.api:
            yield ep

    def get_metadata(self, items: Iterable[Tuple[str, str]]) -> Sequence[Tuple[str, str]]:
        """
        Filter allowed headers
        """
        pats = self._conf.forward_headers
        return tuple((k, v) for k, v in items if any(map(lambda pat:  fnmatch(k, pat), pats)))

    async def _run_health_check(self):
        ServingStatus = health_pb2.HealthCheckResponse.ServingStatus
        stub = health_pb2_grpc.HealthStub(self._channel)
        while self._connected:
            request = health_pb2.HealthCheckRequest(service="QgisServer")
            try:
                async for resp in stub.Watch(request):
                    self._status = "available"
                    match resp.status:
                        case ServingStatus.SERVING:
                            logger.info("Backend: %s: status changed to SERVING", self._address)
                            self._serving = True
                        case ServingStatus.NOT_SERVING:
                            logger.info("Backend: %s: status changed to NOT_SERVING", self._address)
                            self._serving = False
                        case other:
                            logger.error("Backend: %s, status changed to: %s", self._address, other)
                            self._serving = False
                    if not self._connected:
                        break
            except grpc.RpcError as rpcerr:
                if rpcerr.code() != grpc.StatusCode.UNAVAILABLE:
                    self._serving = False
                    logger.error(
                        "Backend error:\t%s\t%s\t%s",
                        self._address,
                        rpcerr.code(),
                        rpcerr.details(),
                    )
                else:
                    if self._status != "unavailable":
                        self._status = "unavailable"
                        logger.error("Backend: %s: UNAVAILABLE", self._address)
            if self._connected:
                await asyncio.sleep(5)

    async def close(self, with_grace_period: bool = False):

        self._closing = True
        if not self._channel:
            return

        if self.in_use and with_grace_period:
            # Apply grace period
            logger.debug("** Applying grace period for channel %s", self.address)
            await asyncio.sleep(self.timeout)

        if self.in_use:
            logger.error(f"Closing channel {self.address} while in use")

        self._connected = False
        logger.debug(
            "Closing backend '%s' (grace period: %s)",
            self._address,
            with_grace_period,
        )
        if self._health_check:
            self._health_check.cancel()
            self._health_check = None
        await self._channel.close()
        self._channel = None

    async def connect(self) -> bool:
        assert not self._connected  # nosec
        logger.debug("Backend: connecting to %s", self._address)
        try:
            self._channel = grpc.aio.secure_channel(
                self._address,
                self._ssl_creds,
                options=CHANNEL_OPTIONS,
            ) if self._use_ssl else grpc.aio.insecure_channel(
                self._address,
                options=CHANNEL_OPTIONS,
            )
            self._connected = True
            self._health_check = asyncio.create_task(self._run_health_check())
        except grpc.RpcError as rpcerr:
            logger.error(
                "gRPC Error:\t%s\t%s\t%s",
                self._address,
                rpcerr.code(),
                rpcerr.details(),
            )
            # Unrecoverable error ?
            if rpcerr.code() != grpc.StatusCode.UNAVAILABLE:
                raise
        return self._connected

    @asynccontextmanager
    async def stub(self, unknown_error_callback: Optional[Callable] = None):
        """ Return a server stub from the current channel
        """
        if not self._serving or self._closing:
            raise web.HTTPServiceUnavailable()

        self._usecount += 1
        try:
            yield api_pb2_grpc.QgisServerStub(self._channel)
        except grpc.RpcError as rpcerr:
            logger.error(
                "Backend error:\t%s\t%s\t%s",
                self._address,
                rpcerr.code(),
                rpcerr.details(),
            )

            match rpcerr.code():
                case grpc.StatusCode.NOT_FOUND:
                    raise web.HTTPNotFound()
                case grpc.StatusCode.UNAVAILABLE:
                    raise web.HTTPServiceUnavailable()
                case grpc.StatusCode.PERMISSION_DENIED:
                    raise web.HTTPForbidden()
                case grpc.StatusCode.INVALID_ARGUMENT:
                    raise web.HTTPBadRequest()
                case grpc.StatusCode.INTERNAL:
                    raise web.HTTPInternalServerError()
                case grpc.StatusCode.UNKNOWN:
                    # Code is outside of gRPC namespace
                    # Let the caller handle it in case
                    # the real error code was in initial metadata
                    if unknown_error_callback:
                        unknown_error_callback(rpcerr.initial_metadata())
                    else:
                        raise
                case _:
                    # Unhandled error
                    raise
        finally:
            self._usecount -= 1
