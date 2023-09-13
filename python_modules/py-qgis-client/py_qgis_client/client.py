""" Qgis worker client
"""
import asyncio
import grpc
from .._grpc import api_pb2
from .._grpc import api_pb2_grpc

from grpc_health.v1 import health_pb2       # HealthCheckRequest
from grpc_health.v1 import health_pb2_grpc  # HealthStub

import os
import sys

from pydantic import (
    Field,
    PlainValidator,
    PlainSerializer,
    WithJsonSchema,
)

from urllib.parse import urlsplit, urlunsplit, SplitResult,
from pathlib import Path
from contextlib import asynccontextmanager
from typing_extensions import (
    Optional,
    List,
    Tuple,
    Sequence,
    Annotated,
    Self,
    AsyncIterator,
)

from py-qgis-contrib.core import config, logger


# For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html
CHANNEL_OPTIONS = [
    ("grpc.lb_policy_name", "round_robin"),
    ("grpc.enable_retries", 1),
    ("grpc.keepalive_timeout_ms", 10000),
]

def _validate_address(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("str expected")
    url = urlsplit(v)
    if url.scheme == "unix":
        
    if not url.scheme:
        url = url._replace(scheme='file')
    return url


class ClientConfig(config.Config):
    server_address: config.Address = Field(
        title="TCP or Socket address"
        description="Address of worker client"
    )
    use_ssl: bool = False
    ssl_files: Optional[config.SSLConfig] = None


# Return a ChannelCredential struct
def _channel_credentials(files: SSLConfig):
    def _read(f) -> Optional[bytes]:
        if f:
            with Path(files.ca).open('rb') as fp:
                return fp.read()

    return grpc.ssl_channel_credentials(
        root_certificate=_read(files.ca),
        certificat=_read(files.cert),
        private_key=_read(files.key),
    )

c


class Client:
    def __init__(
        self,
        config: ClientConfig
        metadata: Optional[Sequence[Tuple[str, str]]] = None
    ):
        self._server_address = server_address
        self._use_ssl = config.use_ssl
        if self._use_ssl:
            self._ssl_creds = _channel_credentials(ssl_files)
        else:
            self._ssl_creds = None
        
        match config.server_address:
            case (host, port):
                self._server_address = f"{host}:{port}"
            case socket :
                self._server_address = socket

        self._server_address 
        self._metadata = metadata

        # Cached channel and stub
        self._api_channel = None
        self._api_stub = None

        self._server_status = ServingStatus.NOT_SERVING

    @asynccontextmanager
    async def _channel(self) -> grpc.aio.Channel:
        with (
            grpc.aio.secure_channel(
                self._server_address,
                self._ssl_creds,
                options=CHANNEL_OPTIONS,
            )
            if self._use_ssl
            else grpc.insecure_channel(
                self._server_address,
                options=CHANNEL_OPTIONS,
            )
        ) as channel:
                yield channel

    async def ping(self, echo: str, count: int = 1, timeout: int = 20) -> AsyncIterator[str]:
        """ Ping the remote service
        """
        with self._channel():
            stub = api_pb2_grpc.QgisWorkerStub(channel)
            for in range(count):
                resp = await stub.Ping(
                    api_pb2.PingRequest(echo=echo),
                    timeout=timeout,
                )
                yield resp.echo

    async def _watch(self):
        """ Watch service status
        """
        ServingStatus = health_pb2.HealthCheckResponse.ServingStatus
        try:
            with self._channel() as channel:
                stub = health_pb2_grpc.HealthStub(channel)
                request = await health_pb2.HealthCheckRequest(service="QgisWorker")
                async for resp in stub.Watch(request):
                    self._server_status = resp.status
                    logger.debug(
                        "HEALTHCHECK status for %s: %s",
                        self._server_address,
                        ServingStatus.Name(resp.status),
                    ) 
        except grpc.RpcError as rpcerr:
            logger.error("HEALTHCHECK\t%s\t%s", rpcerr.code(), rpcerr.details())

