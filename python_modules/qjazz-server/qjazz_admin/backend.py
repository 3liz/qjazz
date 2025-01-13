""" Qgis worker client
"""
import asyncio
import json

from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import (
    AsyncGenerator,
    AsyncIterator,
    Dict,
    Optional,
    Self,
    Tuple,
    Type,
    overload,
)

import grpc

from grpc_health.v1 import (
    health_pb2,  # HealthCheckRequest
    health_pb2_grpc,  # HealthStub
)
from pydantic import Field, IPvAnyAddress, Json

from qjazz_contrib.core import config, logger
from qjazz_rpc._grpc import qjazz_pb2, qjazz_pb2_grpc


class ShutdownInProgress(Exception):
    pass


ServingStatus = health_pb2.HealthCheckResponse.ServingStatus

# For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html
CHANNEL_OPTIONS = [
    ("grpc.lb_policy_name", "pick_first"),
    ("grpc.enable_retries", 1),
    ("grpc.keepalive_timeout_ms", 10000),
]


class BackendConfig(config.ConfigBase):
    server_address: Tuple[IPvAnyAddress, int] = Field(
        title="TCP address",
        description="Address of RPC service",
    )
    use_ssl: bool = False
    ssl: config.SSLConfig = config.SSLConfig()

    def address_to_string(self) -> str:
        """ Returns the address as string
        """
        return f"{self.server_address[0]}:{self.server_address[1]}"


#
# Admin single client
# to only **one** instance a gRPC server
#

RECONNECT_DELAY = 3


class Backend:
    """ Client that target a
        single gRPC instance from its ip address
        or a unix socket.
    """

    def __init__(
        self,
        conf: BackendConfig,
        grace_period: int = 0,
    ):
        self._channel = None
        # 'connected' is a bit overstated here, we'are online
        # but that does not mean necessarly that we are connected
        # to a backend server
        self._connected = 0
        self._address = conf.address_to_string()
        self._use_ssl = conf.use_ssl
        self._shutdown = False
        self._grace_period = grace_period
        self._shutdown_task: asyncio.Task|None = None

        def _read_if(f):
            if f:
                with f.open('rb') as fp:
                    return fp.read()

        self._ssl_creds = grpc.ssl_channel_credentials(
            root_certificates=_read_if(conf.ssl.cafile),
            certificate_chain=_read_if(conf.ssl.certfile),
            private_key=_read_if(conf.ssl.keyfile),
        ) if self._use_ssl else None

    async def shutdown(self):
        """ Shutdown the server
        """
        logger.trace("Shutdown called for", self._address)
        self._shutdown = True
        self._cancel_shutdown_task()
        await self._close()

    def _cancel_shutdown_task(self):
        if self._shutdown_task:
            logger.trace("Concelling shutdown task for %s", self._address)
            self._shutdown_task.cancel()
            self._shutdown_task = None

    async def _graceful_shutdown_task(self):
        """ Perform a shutdown with a grace period
            If another task has required the connection
            then the task shutdown should be cancelled
        """
        await asyncio.sleep(self._grace_period)
        if self._connected == 0:
            await self._close()

    @property
    def address(self) -> str:
        return self._address

    async def _close(self):
        if self._channel:
            # Avoid race condition
            channel = self._channel
            self._channel = None
            logger.debug("Closing channel '%s'", self._address)
            await channel.close()

    async def _connect(self) -> grpc.Channel:
        if self._channel is not None:
            return self._channel

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
            return self._channel
        except grpc.RpcError as rpcerr:
            logger.error(
                "Backend error:\t%s\t%s\t%s",
                self._address,
                rpcerr.code(),
                rpcerr.details(),
            )
            # Unrecoverable error ?
            raise

    @overload
    def _stub(
        self,
        factory: Type[qjazz_pb2_grpc.QgisAdminStub] = qjazz_pb2_grpc.QgisAdminStub,
    ) -> AbstractAsyncContextManager[qjazz_pb2_grpc.QgisAdminStub]:
        ...

    @overload
    def _stub(self, factory: Type[health_pb2_grpc.HealthStub],
    ) -> AbstractAsyncContextManager[health_pb2_grpc.HealthStub]:
        ...

    @asynccontextmanager
    async def _stub(
        self,
        factory = qjazz_pb2_grpc.QgisAdminStub,
    ) -> AsyncGenerator:
        async with self.connection() as channel:
            yield factory(channel)

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[grpc.Channel, None]:
        # There is shutdown in progress
        if self._shutdown:
            raise ShutdownInProgress(self._address)
        # Abort shutdown task
        self._cancel_shutdown_task()
        # Connect if needed
        channel = await self._connect()
        try:
            self._connected += 1
            yield channel
        finally:
            self._connected -= 1
            if self._connected == 0:
                if self._grace_period:
                    # Handle grace period
                    self._shutdown_task = asyncio.create_task(
                        self._graceful_shutdown_task(),
                    )
                else:
                    # Shutdown immediatly
                    await self._close()

    async def ping(
        self,
        echo: str,
        count: int = 1,
        timeout: int = 20,
    ) -> AsyncIterator[Optional[str]]:
        """ Ping the remote ervice

            Return none if the service is not reachable
        """
        async with self._stub() as stub:
            for _ in range(count):
                try:
                    resp = await stub.Ping(
                        qjazz_pb2.PingRequest(echo=echo),
                        timeout=timeout,
                    )
                    yield resp.echo
                except grpc.RpcError as rpcerr:
                    if rpcerr.code() == grpc.StatusCode.UNAVAILABLE:
                        yield None
                    else:
                        raise

    async def serving(self) -> bool:
        """  Check if remote is serving
        """
        try:
            async with self._stub(health_pb2_grpc.HealthStub) as stub:
                request = health_pb2.HealthCheckRequest(service="QgisAdmin")
                resp = await stub.Check(request)
                return resp.status == ServingStatus.SERVING
        except grpc.RpcError as rpcerr:
            if rpcerr.code() == grpc.StatusCode.UNAVAILABLE:
                return False
            else:
                logger.error("%s\t%s\t%s", self._address, rpcerr.code(), rpcerr.details())
                raise

    async def watch(self) -> AsyncIterator[Tuple[Self, bool]]:
        """ Watch service status
        """
        serving = False
        async with self._stub(health_pb2_grpc.HealthStub) as stub:
            while not self._shutdown:
                try:
                    request = health_pb2.HealthCheckRequest(service="QgisAdmin")
                    async for resp in stub.Watch(request):
                        logger.debug(
                            "%s\tStatus changed to %s",
                            self._address,
                            ServingStatus.Name(resp.status),
                        )
                        serving = resp.status == ServingStatus.SERVING
                        yield self, serving
                        if self._shutdown:
                            break
                except grpc.RpcError as rpcerr:
                    if serving:
                        serving = False
                        yield self, serving
                    # Forward exception
                    if rpcerr.code() != grpc.StatusCode.UNAVAILABLE:
                        logger.error("%s\t%s\t%s", self._address, rpcerr.code(), rpcerr.details())
                        raise
                        logger.trace("Backend: %s: UNAVAILABLE", self._address)
                # Attempt reconnection
                if not self._shutdown:
                    logger.debug("Waiting for reconnection of %s", self._address)
                    await asyncio.sleep(RECONNECT_DELAY)

    #
    # Cache
    #

    async def checkout_project(
        self,
        project: str,
        pull: bool = False,
    ) -> qjazz_pb2.CacheInfo:
        """ Checkout PROJECT from cache
        """
        async with self._stub() as stub:
            return stub.CheckoutProject(
                qjazz_pb2.CheckoutRequest(uri=project, pull=pull),
            )

    async def drop_project(self, project: str) -> qjazz_pb2.CacheInfo:
        """ Drop PROJECT from cache
        """
        async with self._stub() as stub:
            return  stub.DropProject(
                qjazz_pb2.DropRequest(uri=project),
            )

    async def clear_cache(self) -> None:
        """ Clear cache
        """
        async with self._stub() as stub:
            await stub.ClearCache(qjazz_pb2.Empty())

    async def list_cache(self) -> AsyncIterator[qjazz_pb2.CacheInfo]:
        """ List projects from cache
        """
        async with self._stub() as stub:
            async for item in stub.ListCache(qjazz_pb2.Empty()):
                yield item

    async def project_info(self, project: str) -> qjazz_pb2.ProjectInfo:
        """ Return info from PROJECT in cache
        """
        async with self._stub() as stub:
            return await stub.GetProjectInfo(
                qjazz_pb2.ProjectRequest(uri=project),
            )

    async def pull_projects(self, *uris) -> AsyncIterator[qjazz_pb2.CacheInfo]:
        """ Pull/Update projects in cache
        """
        async with self._stub() as stub:
            for uri in uris:
                yield await stub.CheckoutProject(qjazz_pb2.CheckoutRequest(uri=uri, pull=True))

    async def catalog(self, location: Optional[str] = None) -> AsyncIterator[qjazz_pb2.CatalogItem]:
        """ List projects from cache
        """
        async with self._stub() as stub:
            async for item in stub.Catalog(
                qjazz_pb2.CatalogRequest(location=location),
            ):
                yield item

    #
    # Plugins
    #

    async def list_plugins(self) -> AsyncIterator[qjazz_pb2.PluginInfo]:
        """ List projects from cache
        """
        async with self._stub() as stub:
            async for item in stub.ListPlugins(qjazz_pb2.Empty()):
                yield item

    #
    # Config
    #

    async def get_config(self) -> Json:
        """ Get server configuration
        """
        async with self._stub() as stub:
            resp = await stub.GetConfig(qjazz_pb2.Empty())
            return resp.json

    async def set_config(self, config: Dict | Json) -> None:
        """ Send CONFIG to remote
        """
        if isinstance(config, dict):
            config = json.dumps(config)
        async with self._stub() as stub:
            await stub.SetConfig(qjazz_pb2.JsonConfig(json=config))

    #
    #  status
    #
    async def get_env(self) -> Json:
        """ Get environment status
        """
        async with self._stub() as stub:
            resp = await stub.GetEnv(qjazz_pb2.Empty())
            return resp.json

    async def enable_server(self, enable: bool):
        """ Enable/Disable qgis server serving state
        """
        async with self._stub() as stub:
            _ = await stub.SetServerServingStatus(
                qjazz_pb2.ServerStatus(
                    status=qjazz_pb2.ServingStatus.SERVING,
                )
                if enable
                else qjazz_pb2.ServerStatus(
                    status=qjazz_pb2.ServingStatus.NOT_SERVING,
                ),
            )

    async def stats(self) -> qjazz_pb2.StatsReply:
        async with self._stub() as stub:
            return await stub.Stats(qjazz_pb2.Empty())

    async def watch_stats(
        self,
        interval: int = 3,
    ) -> AsyncIterator[Tuple[Self, Optional[qjazz_pb2.StatsReply]]]:
        """ Watch service stats
        """
        while not self._shutdown:
            try:
                async with self._stub() as stub:
                    while True:
                        resp = await stub.Stats(qjazz_pb2.Empty())
                        yield (self, resp)
                        if self._shutdown:
                            break
                        await asyncio.sleep(interval)
            except grpc.RpcError as rpcerr:
                logger.trace(
                    "Stats request failed: %s\t%s",
                    self._address,
                    rpcerr.details(),
                )
                if rpcerr.code() == grpc.StatusCode.UNAVAILABLE:
                    yield (self, None)
                else:
                    # Forward exception
                    raise
            if not self._shutdown:
                await asyncio.sleep(RECONNECT_DELAY)

    async def sleep(self, delay: int) -> qjazz_pb2.Empty:
        async with self._stub() as stub:
            return await stub.Sleep(qjazz_pb2.SleepRequest(delay=delay))
