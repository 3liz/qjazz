import grpc
from ._grpc import api_pb2
from ._grpc import api_pb2_grpc

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import (
    Generator,
    Tuple,
    Any,
    Iterable,
)

import asyncio
import traceback
import json

from py_qgis_contrib.core import logger

from . import messages as _m

from .worker import Worker, WorkerError

#
# https://grpc.github.io/grpc/python/
#


def _match_grpc_code(code: int) -> grpc.StatusCode:
    match code:
        case 403:
            return grpc.StatusCode.PERMISSION_DENIED
        case 404 | 410:
            return grpc.StatusCode.NOT_FOUND
        case 405:
            return grpc.StatusCode.UNIMPLEMENTED
        case 500:
            return grpc.StatusCode.INTERNAL
        case _:
            return grpc.StatusCode.UNKNOWN


def _headers_to_metadata(coll: Iterable[Tuple[str, Any]]):
    return ((f"x-reply-header-{k.lower()}", str(v)) for k, v in coll)


def _to_iso8601(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec='milliseconds')


async def _abort_on_error(context: grpc.aio.ServicerContext, code: int, details: str, request: str):
    logger.log_req("%s\t%s\t%s", code, request, details)
    await context.send_initial_metadata(
        [('x-reply-status-code', str(code))]
    )
    await context.abort(_match_grpc_code(code), details)


class ExecError(Exception):
    pass


class RpcService(api_pb2_grpc.QgisWorkerServicer):
    """ Worker API
    """

    def __init__(self, worker: Worker):
        super().__init__()
        self._worker = worker
        self._lock = asyncio.Lock()
        self._timeout = worker.config.worker_timeout
        self._max_requests = worker.config.max_waiting_requests
        self._count = 0
        self._cached_worker_env = None
        self._cached_worker_plugins = None

    async def cache_worker_status(self):
        # Cache environment since it is immutable
        logger.debug("Caching worker status")
        self._cached_worker_env = await self._worker.env()
        _, items = await self._worker.list_plugins()
        if items:
            self._cached_worker_plugins = [item async for item in items]
        else:
            self._cached_worker_plugins = []

    async def Ping(
        self,
        request: api_pb2.PingRequest,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.PingReply:
        """  Simple ping request
        """
        logger.log_req("Received PING request")
        return api_pb2.PingReply(echo=request.echo)

    @asynccontextmanager
    async def lock(self, context, request: str):
        """ Lock context

            - Prevent race condition on worker
            - Prevent request piling
            - Handle client disconnection
            - Handle execution errors
            - Handle stalled/long running job
        """
        try:
            # Note: identities are not set if the connection is not
            # authenticated
            # logger.trace("Peer identities: %s", context.peer_identities())
            _on_air = False
            if self._count >= self._max_requests:
                raise WorkerError(503, "Maximum number of waiting requests reached")
            if not self._worker.is_alive():
                raise WorkerError(503, "Server shutdown")
            # Prevent race condition
            await asyncio.wait_for(self._lock.acquire(), self._timeout)
            self._count += 1
            _on_air = True
            yield
        except asyncio.TimeoutError:
            logger.critical("Worker stalled, terminating...")
            self._worker.terminate()
            await _abort_on_error(context, 503, "Server stalled", request)
        except WorkerError as e:
            await _abort_on_error(context, e.code, e.details, request)
        except asyncio.CancelledError:
            logger.error("Connection cancelled by client")
            if _on_air:
                # Flush stream from current task
                await self._worker.wait_until_task_done()
        except Exception as err:
            logger.critical(traceback.format_exc(), request)
            await _abort_on_error(context, 500, str(err), request)
        finally:
            self._count -= 1
            self._lock.release()

    #
    # OWS request
    #
    async def ExecuteOwsRequest(
        self,
        request: api_pb2.OwsRequest,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.ResponseChunk, None, None]:

        async with self.lock(context, "ExecuteOwsRequest"):
            headers = dict(context.invocation_metadata())

            resp, stream = await self._worker.ows_request(
                service=request.service,
                request=request.request,
                version=request.version,
                options=request.options,
                target=request.target,
                url=request.url,
                direct=request.direct,
                headers=headers,
                request_id=request.request_id,
                debug_report=request.debug_report,
            )

            # Send Headers
            metadata = list(_headers_to_metadata(resp.headers.items()))
            metadata.append(('x-reply-status-code', str(resp.status_code)))
            await context.send_initial_metadata(metadata)

            # Send data
            yield api_pb2.ResponseChunk(chunk=resp.data)
            if stream:
                async for chunk in stream:
                    yield api_pb2.ResponseChunk(chunk=chunk)

            # Final report
            if request.debug_report:
                logger.trace("Sending debug report")
                report = await self._worker.io.read()
                context.set_trailling_metatada([
                    ('x-debug-memory', str(report.memory)),
                    ('x-debug-duration', str(report.duration)),
                    ('x-debug-timestamp', str(report.timestamp)),
                ])

    #
    # Generic request
    #

    async def ExecuteRequest(
        self,
        request: api_pb2.GenericRequest,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.ResponseChunk, None, None]:

        async with self.lock(context, "ExecuteRequest"):
            headers = dict(context.invocation_metadata())

            try:
                http_method = _m.HTTPMethod[request.method]
            except KeyError:
                status = 405
                resp = f"Invalid method {request.method}"
                raise ExecError

            status, stream = await self._worker.request(
                url=request.url,
                method=http_method,
                data=request.data,
                target=request.target,
                direct=request.direct,
                headers=headers,
                request_id=request.request_id,
                debug_report=request.debug_report,
            )

            # Send Headers
            metadata = list(_headers_to_metadata(resp.headers.items()))
            metadata.append(('x-reply-status-code', str(resp.status_code)))
            await context.send_initial_metadata(metadata)

            # Send data
            yield api_pb2.ResponseChunk(chunk=resp.data)
            if stream:
                async for chunk in stream:
                    yield api_pb2.ResponseChunk(chunk=chunk)

            # Final report
            if request.debug_report:
                report = await self._worker.io.read()
                context.set_trailling_metatada([
                    ('x-debug-memory', str(report.memory)),
                    ('x-debug-duration', str(report.duration)),
                    ('x-debug-timestamp', str(report.timestamp)),
                ])

    #
    # Checkout project
    #

    async def CheckoutProject(
        self,
        request: api_pb2.CheckoutRequest,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.CacheInfo:

        async with self.lock(context, "CheckoutProject"):
            resp = await self._worker.checkout_project(
                uri=request.uri,
                pull=request.pull,
            )
            return _new_cache_info(resp)

    #
    # Drop project
    #
    async def DropProject(
        self,
        request: api_pb2.CheckoutRequest,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.CacheInfo:

        async with self.lock(context, "DropProject"):
            resp = await self._worker.drop_project(uri=request.uri)
            return _new_cache_info(resp)

    #
    # Cache list
    #
    async def ListCache(
        self,
        request: api_pb2.ListRequest,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.CacheInfo, None, None]:

        async with self.lock(context, "ListCache"):
            try:
                status_filter = _m.CheckoutStatus[request.status_filter]
            except KeyError:
                status_filter = ""

            count, items = await self._worker.list_cache(status_filter)
            await context.send_initial_metadata([("x-reply-header-cache-count", str(count))])
            if items:
                async for item in items:
                    yield _new_cache_info(item)

    #
    # Clear cache
    #
    async def ClearCache(
        self,
        request: api_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.Empty:

        async with self.lock(context, "ClearCache"):
            await self._worker.clear_cache()
            return api_pb2.Empty()

    #
    # List Catalog Items
    #
    async def Catalog(
        self,
        request: api_pb2.CatalogRequest,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.CatalogItem, None, None]:

        async with self.lock(context, "Catalog"):
            items = await self._worker.catalog(location=request.location)
            async for item in items:
                yield api_pb2.CatalogItem(
                    uri=item.uri,
                    name=item.name,
                    storage=item.storage,
                    last_modified=_to_iso8601(datetime.fromtimestamp(item.last_modified)),
                    public_uri=item.public_uri,
                )

    #
    # Project info
    #
    async def GetProjectInfo(
        self,
        request: api_pb2.ProjectRequest,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.ProjectInfo:

        def _layer(layer):
            return api_pb2.ProjectInfo.Layer(
                layer_id=layer.layer_id,
                name=layer.name,
                source=layer.source,
                crs=layer.crs,
                is_valid=layer.is_valid,
                is_spatial=layer.is_spatial,
            )

        async with self.lock(context, "GetProjectInfo"):
            resp = await self._worker.io.project_info(uri=request.uri)
            return api_pb2.ProjectInfo(
                status=resp.status.name,
                uri=resp.uri,
                filename=resp.filename,
                crs=resp.crs,
                last_modified=_to_iso8601(datetime.fromtimestamp(resp.last_modified)),
                storage=resp.storage,
                has_bad_layers=resp.has_bad_layers,
                layers=[_layer(layer) for layer in resp.layers],
            )

    #
    # Plugin list
    #
    async def ListPlugins(
        self,
        request: api_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.PluginInfo, None, None]:

        if self._cached_worker_plugins is None:
            async with self.lock(context, "ListPlugins"):
                await self.cache_worker_status()

        count = len(self._cached_worker_plugins)
        await context.send_initial_metadata([("x-reply-header-installed-plugins", str(count))])
        for item in self._cached_worker_plugins:
            yield api_pb2.PluginInfo(
                name=item.name,
                path=str(item.path),
                plugin_type=item.plugin_type.name,
                json_metadata=json.dumps(item.metadata),
            )

    #
    # Get config
    #
    async def GetConfig(
        self,
        request: api_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.JsonConfig:

        try:
            retval = self._worker.dump_config()
            return api_pb2.JsonConfig(json=json.dumps(retval))
        except WorkerError as e:
            await _abort_on_error(context, e.status, e.details, "GetConfig")
        except Exception as err:
            logger.critical(traceback.format_exc())
            await _abort_on_error(context, 500, str(err), "GetConfig")

    #
    # Set Config
    #
    async def SetConfig(
        self,
        request: api_pb2.JsonConfig,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.Empty:

        try:
            obj = json.loads(request.json)
        except json.JSONDecodeError as err:
            await _abort_on_error(context, 400, str(err), "SetConfig")

        async with self.lock(context, "SetConfig"):
            await self._worker.update_config(obj)
            # Update configuration
            self._timeout = self._worker.config.worker_timeout
            self._max_requests = self._worker.config.max_waiting_requests
            return api_pb2.Empty()

    #
    # Get Env Status
    #
    async def GetEnv(
        self,
        request: api_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.JsonConfig, None, None]:

        if self._cached_worker_env is None:
            async with self.lock(context, "GetEnv"):
                await self.cache_worker_status()

        try:
            return api_pb2.JsonConfig(json=json.dumps(self._cached_worker_env))
        except WorkerError as e:
            await _abort_on_error(context, e.status, e.details, "GetEnv")
        except Exception as err:
            logger.critical(traceback.format_exc())
            await _abort_on_error(context, 500, str(err), "GetEnv")

#
# Build a cache info from response
#


def _new_cache_info(resp) -> api_pb2.CacheInfo:
    if resp.last_modified:
        last_modified = _to_iso8601(datetime.fromtimestamp(resp.last_modified))
    else:
        last_modified = ""

    return api_pb2.CacheInfo(
        uri=resp.uri,
        status=resp.status.name,
        in_cache=resp.in_cache,
        name=resp.name,
        storage=resp.storage,
        last_modified=last_modified,
        saved_version=resp.saved_version or "",
        debug_metadata=resp.debug_metadata,
    )
