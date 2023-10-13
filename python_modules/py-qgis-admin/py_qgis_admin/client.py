""" Qgis worker client
"""
import asyncio
import grpc

from py_qgis_worker._grpc import (
    api_pb2,
    api_pb2_grpc,
)

from grpc_health.v1 import health_pb2       # HealthCheckRequest
from grpc_health.v1 import health_pb2_grpc  # HealthStub

import json

from pydantic import (
    Field,
)

from pathlib import Path
from contextlib import asynccontextmanager
from typing_extensions import (
    Optional,
    Dict,
    Tuple,
    Sequence,
    AsyncIterator,
    Self,
)

from py_qgis_contrib.core import config, logger


ServingStatus = health_pb2.HealthCheckResponse.ServingStatus

# For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html
CHANNEL_OPTIONS = [
    ("grpc.lb_policy_name", "pick_first"),
    ("grpc.enable_retries", 0),
    ("grpc.keepalive_timeout_ms", 10000),
]


class ClientConfig(config.Config):
    server_address: config.NetInterface = Field(
        title="TCP or Socket address",
        description="Address of worker client",
    )
    use_ssl: bool = False
    ssl_files: Optional[config.SSLConfig] = None

    def address_to_string(self) -> str:
        """ Returns the address as string
        """
        match self.server_address:
            case (host, port):
                return f"{host}:{port}"
            case socket:
                return socket


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


#
# Admin single client
# to only **one** instance a gRPC server
#

RECONNECT_DELAY = 3


class PoolItemClient:
    """ Client that target a
        single gRPC instance from its ip address
        or a unix socket.
    """

    def __init__(
        self,
        config: ClientConfig,
        metadata: Optional[Sequence[Tuple[str, str]]] = None,
    ):
        self._server_address = config.server_address
        self._use_ssl = config.use_ssl
        if self._use_ssl:
            self._ssl_creds = _channel_credentials(config.ssl_files)
        else:
            self._ssl_creds = None

        self._server_address = config.address_to_string()
        self._metadata = metadata
        self._env = None
        self._shutdown = False

    def shutdown(self):
        """ Shutdown the server
        """
        self._shutdown = True

    @property
    def address(self) -> str:
        return self._server_address

    @asynccontextmanager
    async def _channel(self) -> grpc.aio.Channel:
        logger.trace("Connecting to %s", self.address)
        async with (
            grpc.aio.secure_channel(
                self._server_address,
                self._ssl_creds,
                options=CHANNEL_OPTIONS,
            )
            if self._use_ssl
            else grpc.aio.insecure_channel(
                self._server_address,
                options=CHANNEL_OPTIONS,
            )
        ) as channel:
            yield channel

    @asynccontextmanager
    async def _stub(self) -> api_pb2_grpc.QgisAdminStub:
        async with self._channel() as channel:
            yield api_pb2_grpc.QgisAdminStub(channel)

    async def ping(
        self,
        echo: str,
        count: int = 1,
        timeout: int = 20
    ) -> AsyncIterator[Optional[str]]:
        """ Ping the remote ervice

            Return none if the service is not reachable
        """
        async with self._stub() as stub:
            for _ in range(count):
                try:
                    resp = await stub.Ping(
                        api_pb2.PingRequest(echo=echo),
                        timeout=timeout,
                    )
                    yield resp.echo
                except grpc.RpcError as rpcerr:
                    if rpcerr.code() == grpc.StatusCode.UNAVAILABLE:
                        yield None
                    else:
                        raise

    async def check(self) -> bool:
        """  Check if remote is serving
        """
        try:
            async with self._channel() as channel:
                stub = health_pb2_grpc.HealthStub(channel)
                request = health_pb2.HealthCheckRequest(service="QgisAdmin")
                resp = await stub.Check(request)
                return resp.status == ServingStatus.SERVING
        except grpc.RpcError as rpcerr:
            logger.error("%s\t%s\t%s", self._server_address, rpcerr.code(), rpcerr.details())
            if rpcerr.code() == grpc.StatusCode.UNAVAILABLE:
                return False
            else:
                raise

    async def watch(self) -> AsyncIterator[Tuple[Self, bool]]:
        """ Watch service status
        """
        serving = False
        while not self._shutdown:
            try:
                async with self._channel() as channel:
                    stub = health_pb2_grpc.HealthStub(channel)
                    request = health_pb2.HealthCheckRequest(service="QgisAdmin")
                    async for resp in stub.Watch(request):
                        logger.info(
                            "%s\tStatus changed to %s",
                            self._server_address,
                            ServingStatus.Name(resp.status),
                        )
                        serving = resp.status == ServingStatus.SERVING
                        yield self, serving
                        if self._shutdown:
                            break
            except grpc.RpcError as rpcerr:
                logger.trace("%s\t%s\t%s", self._server_address, rpcerr.code(), rpcerr.details())
                if serving:
                    serving = False
                    yield self, serving
                # Forward exception
                if rpcerr.code() != grpc.StatusCode.UNAVAILABLE:
                    raise
            # Attempt reconnection
            if not self._shutdown:
                logger.debug("Waiting for reconnection of %s", self.address)
                await asyncio.sleep(RECONNECT_DELAY)

    #
    # Cache
    #

    async def checkout_project(
        self,
        project: str,
        pull: bool,
    ) -> AsyncIterator[api_pb2.CacheInfo]:
        """ Checkout PROJECT from cache
        """
        async with self._stub() as stub:
            async for item in stub.CheckoutProject(
                api_pb2.CheckoutRequest(uri=project, pull=pull)
            ):
                yield item

    async def drop_project(self, project: str) -> AsyncIterator[api_pb2.CacheInfo]:
        """ Drop PROJECT from cache
        """
        async with self._stub() as stub:
            async for item in stub.DropProject(
                api_pb2.DropRequest(uri=project)
            ):
                yield item

    async def clear_cache(self) -> None:
        """ Clear cache
        """
        async with self._stub() as stub:
            logger.debug("Cleaning cache for '%s'", self.address)
            await stub.ClearCache(api_pb2.Empty())

    async def list_cache(self, status: str = "") -> AsyncIterator[api_pb2.CacheInfo]:
        """ List projects from cache
        """
        async with self._stub() as stub:
            async for item in stub.ListCache(
                api_pb2.ListRequest(status_filter=status)
            ):
                yield item

    async def project_info(self, project: str) -> AsyncIterator[api_pb2.ProjectInfo]:
        """ Return info from PROJECT in cache
        """
        async with self._stub() as stub:
            async for item in stub.GetProjectInfo(
                api_pb2.ProjectRequest(uri=project)
            ):
                yield item

    async def pull_projects(self, *uris) -> AsyncIterator[api_pb2.CacheInfo]:
        """ Pull/Update projects in cache
        """
        async with self._stub() as stub:
            requests = (api_pb2.ProjectRequest(uri=uri) for uri in uris)
            async for item in stub.PullProjects(requests):
                yield item

    async def catalog(self, location: Optional[str] = None) -> AsyncIterator[api_pb2.CatalogItem]:
        """ List projects from cache
        """
        async with self._stub() as stub:
            async for item in stub.Catalog(
                api_pb2.CatalogRequest(location=location)
            ):
                yield item

    #
    # Plugins
    #

    async def list_plugins(self) -> AsyncIterator[api_pb2.PluginInfo]:
        """ List projects from cache
        """
        async with self._stub() as stub:
            async for item in stub.ListPlugins(api_pb2.Empty()):
                yield item

    #
    # Config
    #

    async def get_config(self) -> str:
        """ Get server configuration
        """
        async with self._stub() as stub:
            resp = await stub.GetConfig(api_pb2.Empty())
            return resp.json

    async def set_config(self, config: Dict | str) -> None:
        """ Send CONFIG to remote
        """
        if isinstance(config, dict):
            config = json.dumps(config)
        async with self._stub() as stub:
            await stub.SetConfig(api_pb2.JsonConfig(json=config))

    #
    #  status
    #

    async def get_env(self) -> str:
        """ Get environment status
        """
        if self._env is None:
            async with self._stub() as stub:
                resp = await stub.GetEnv(api_pb2.Empty())
                self._env = resp.json
        return self._env

    async def enable_server(self, enable: bool):
        """ Enable/Disable qgis server serving state
        """
        async with self._stub() as stub:
            _ = await stub.SetServerServingStatus(
                api_pb2.ServerStatus(
                    status=api_pb2.ServingStatus.SERVING
                )
                if enable
                else api_pb2.ServerStatus(
                    status=api_pb2.ServingStatus.NOT_SERVING
                )
            )

    async def server_enabled(self) -> bool:
        """ Return true if the server is
            in serving state
        """
        async with self._channel() as channel:
            stub = health_pb2_grpc.HealthStub(channel)
            request = await health_pb2.HealthCheckRequest(service="QgisServer")
            resp = await stub.Check(request)
            return resp == ServingStatus.SERVING

    async def stats(self) -> api_pb2.StatsReply:
        async with self._stub() as stub:
            return await stub.Stats(api_pb2.Empty())

    async def watch_stats(
        self,
        interval: int = 3
    ) -> AsyncIterator[Tuple[Self, api_pb2.StatsReply]]:
        """ Watch service stats
        """
        while not self._shutdown:
            try:
                async with self._stub() as stub:
                    while True:
                        resp = await stub.Stats(api_pb2.Empty())
                        yield (self, resp)
                        if self._shutdown:
                            break
                        await asyncio.sleep(interval)
            except grpc.RpcError as rpcerr:
                logger.trace(
                    "Stats request failed: %s\t%s",
                    self._server_address,
                    rpcerr.details()
                )
                if rpcerr.code() == grpc.StatusCode.UNAVAILABLE:
                    yield (self, None)
                else:
                    # Forward exception
                    raise
            if not self._shutdown:
                await asyncio.sleep(RECONNECT_DELAY)
