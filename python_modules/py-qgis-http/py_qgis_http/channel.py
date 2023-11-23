import asyncio

from contextlib import asynccontextmanager
from fnmatch import fnmatch
from pathlib import Path

import grpc

from grpc_health.v1 import health_pb2  # HealthCheckRequest
from grpc_health.v1 import health_pb2_grpc  # HealthStub
from tornado.web import HTTPError
from typing_extensions import Iterator, Optional, Sequence, Tuple

from py_qgis_contrib.core import config, logger
from py_qgis_worker._grpc import api_pb2, api_pb2_grpc  # noqa

from .resolver import ApiEndpoint, BackendConfig

CHANNEL_OPTIONS = [
    ("grpc.lb_policy_name", "round_robin"),
    ("grpc.enable_retries", 1),
    ("grpc.keepalive_timeout_ms", 10000),
]

BACKOFF_TIME = 5


# Return a ChannelCredential struct
def _channel_credentials(files: config.SSLConfig):
    def _read(f) -> Optional[bytes]:
        if f:
            with Path(files.ca).open('rb') as fp:
                return fp.read()

    return grpc.ssl_channel_credentials(
        root_certificate=_read(files.ca),
        certificat=_read(files.cert),
        private_key=_read(files.key),
    )


class Channel:
    """ A gRPC channel reconnect itself if a backend
        so we don't need to handle a reconnection task
    """

    def __init__(self, conf: BackendConfig):
        self._conf = conf
        self._channel = None
        self._connected = False
        self._serving = False
        self._health_check = None
        self._address = conf.to_string()
        self._use_ssl = conf.ssl is not None
        self._ssl_creds = _channel_credentials(conf.ssl) if self._use_ssl else None
        self._usecount = 0
        self._closing = False

        self._posix_route = self._conf.route.as_posix()
        self._meta = {
            'ROUTE': '.'.join(self._conf.route.parts[1:]),
        }

    @property
    def in_use(self) -> bool:
        return self._usecount > 0

    @property
    def meta(self) -> str:
        return self._meta

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

    def get_metadata(self, items: Sequence[Tuple[str, str]]) -> Sequence[Tuple[str, str]]:
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
                    logger.error(
                        "Backend error:\t%s\t%s\t%s",
                        self._address,
                        rpcerr.code(),
                        rpcerr.details(),
                    )
                else:
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
        assert not self._connected
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
    async def stub(self):
        """ Return a server stub from the current channel
        """
        if not self._serving or self._closing:
            raise HTTPError(503)

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
                    raise HTTPError(404)
                case grpc.StatusCode.UNAVAILABLE:
                    raise HTTPError(502)
                case _:
                    raise HTTPError(500)
        finally:
            self._usecount -= 1
