import grpc
from ._grpc import api_pb2
from ._grpc import api_pb2_grpc

from grpc_health.v1 import health_pb2

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import time
from typing import (
    Generator,
    Tuple,
    Any,
    Iterable,
    Iterator,
    AsyncIterator,
)

import traceback
import json

from py_qgis_contrib.core import logger

from . import messages as _m

from .pool import WorkerPool, Worker, WorkerError

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


class WorkerMixIn:
    @asynccontextmanager
    async def get_worker(self, context, request: str) -> Worker:
        try:
            async with self._pool.get_worker() as worker:
                yield worker
        except WorkerError as e:
            await _abort_on_error(context, e.code, e.details, request)

    @asynccontextmanager
    async def wait_for_all_workers(self, context, request: str) -> Iterator[Worker]:
        try:
            async with self._pool.wait_for_all_workers() as workers:
                yield workers
        except WorkerError as e:
            await _abort_on_error(context, e.code, e.details, request)


# ======================
# Qgis server service
#
# Serve requests to
# qgis server
# ======================


class QgisServer(api_pb2_grpc.QgisServerServicer, WorkerMixIn):

    def __init__(self, pool: WorkerPool):
        super().__init__()
        self._pool = pool

    async def Ping(
        self,
        request: api_pb2.PingRequest,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.PingReply:
        """  Simple ping request
        """
        logger.debug("QgisServer: Received PING request")
        return api_pb2.PingReply(echo=request.echo)

    #
    # OWS request
    #
    async def ExecuteOwsRequest(
        self,
        request: api_pb2.OwsRequest,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.ResponseChunk, None, None]:

        async with self.get_worker(context, "ExecuteOwsRequest") as worker:
            headers = dict(context.invocation_metadata())
            _t_start = time()
            resp, stream = await worker.ows_request(
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

            chunk = resp.data
            size = len(chunk)

            # Send data
            yield api_pb2.ResponseChunk(chunk=chunk)
            if stream:
                async for chunk in stream:
                    size += len(chunk)
                    yield api_pb2.ResponseChunk(chunk=chunk)

            # Final report
            if request.debug_report:
                logger.trace("Sending debug report")
                report = await worker.io.read()
                context.set_trailling_metatada([
                    ('x-debug-memory', str(report.memory)),
                    ('x-debug-duration', str(report.duration)),
                    ('x-debug-timestamp', str(report.timestamp)),
                ])

            _t_end = time()
            logger.log_req(
                "OWS\t%s\t%s\t%d\t%d",
                request.service,
                request.request,
                size,
                int((_t_end-_t_start)*1000.),
            )

    #
    # Generic request
    #
    async def ExecuteRequest(
        self,
        request: api_pb2.GenericRequest,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.ResponseChunk, None, None]:

        async with self.get_worker(context, "ExecuteRequest") as worker:
            headers = dict(context.invocation_metadata())

            try:
                http_method = _m.HTTPMethod[request.method]
            except KeyError:
                status = 405
                resp = f"Invalid method {request.method}"
                raise ExecError

            status, stream = await worker.request(
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
                report = await worker.io.read()
                context.set_trailling_metatada([
                    ('x-debug-memory', str(report.memory)),
                    ('x-debug-duration', str(report.duration)),
                    ('x-debug-timestamp', str(report.timestamp)),
                ])


# ======================
# Admin service
# ======================


class QgisAdmin(api_pb2_grpc.QgisAdminServicer, WorkerMixIn):

    def __init__(self, pool: WorkerPool, health_servicer):
        super().__init__()
        self._pool = pool
        self._health_servicer = health_servicer

    async def Ping(
        self,
        request: api_pb2.PingRequest,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.PingReply:
        """  Simple ping request
        """
        logger.debug("QgisAdmin Received PING request")
        return api_pb2.PingReply(echo=request.echo)

    async def SetServerServingStatus(
        self,
        request: api_pb2.ServerStatus,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.Empty:
        """ Set the Healthcheck servec service
            status
        """
        ServingStatus = health_pb2.HealthCheckResponse.ServingStatus
        match request.status:
            case api_pb2.ServingStatus.SERVING:
                status = ServingStatus.SERVING
            case api_pb2.ServingStatus.NOT_SERVING:
                status = ServingStatus.NOT_SERVING
        logger.debug(
            "Setting server Healthcheck status to %s",
            ServingStatus.Name(status)
        )
        await self._health_servicer.set("QgisServer", status)
        return api_pb2.Empty()

    #
    # Checkout project
    #
    async def CheckoutProject(
        self,
        request: api_pb2.CheckoutRequest,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.CacheInfo, None, None]:

        async with self.wait_for_all_workers(context, "CheckoutProject") as workers:
            for w in workers:
                resp = await w.checkout_project(
                    uri=request.uri,
                    pull=request.pull,
                )
                yield _new_cache_info(resp)

    #
    # Pull projects
    #
    async def PullProjects(
        self,
        requests: AsyncIterator[api_pb2.ProjectRequest],
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.CacheInfo, None, None]:

        async with self.wait_for_all_workers(context, "PullProjects") as workers:
            async for req in requests:
                for w in workers:
                    resp = await w.checkout_project(uri=req.uri, pull=True)
                yield _new_cache_info(resp)

    #
    # Drop project
    #

    async def DropProject(
        self,
        request: api_pb2.CheckoutRequest,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.CacheInfo, None, None]:

        async with self.wait_for_all_workers(context, "DropProject") as workers:
            for w in workers:
                resp = await self._worker.drop_project(uri=request.uri)
                yield _new_cache_info(resp)

    #
    # Cache list
    #
    async def ListCache(
        self,
        request: api_pb2.ListRequest,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.CacheInfo, None, None]:
        """ Sent cache list from all workers
        """
        try:
            status_filter = _m.CheckoutStatus[request.status_filter]
        except KeyError:
            status_filter = ""

        async with self.wait_for_all_workers(context, "ListCache") as workers:
            count = 0
            cachelist = tuple()
            for w in workers:
                n, items = await w.list_cache(status_filter)
                if items:
                    count += n
                    cachelist += (items,)

            await context.send_initial_metadata([("x-reply-header-cache-count", str(count))])
            for items in cachelist:
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

        async with self.wait_for_all_workers(context, "ClearCache") as workers:
            for w in workers:
                await w.clear_cache()
            return api_pb2.Empty()

    #
    # Update cache
    #
    async def UpdateCache(
        self,
        request: api_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.CacheInfo, None, None]:

        async with self.wait_for_all_workers(context, "UpdateCache") as workers:
            _workers = list(workers)
            _all = set()
            for w in _workers:
                # Collect all items for all workers
                _, items = await w.list_cache()
                if items:
                    _all.update(item.uri async for item in items)
            for uri in _all:
                # Update all items for all workers
                for w in _workers:
                    yield await w.checkout(uri, pull=True)

    #
    # List Catalog Items
    #
    async def Catalog(
        self,
        request: api_pb2.CatalogRequest,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.CatalogItem, None, None]:

        async with self.get_worker(context, "Catalog") as worker:
            items = await worker.catalog(location=request.location)
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
    ) -> Generator[api_pb2.CacheInfo, None, None]:

        def _layer(layer):
            return api_pb2.ProjectInfo.Layer(
                layer_id=layer.layer_id,
                name=layer.name,
                source=layer.source,
                crs=layer.crs,
                is_valid=layer.is_valid,
                is_spatial=layer.is_spatial,
            )

        async with self.wait_for_all_workers(context, "GetProjectInfo") as workers:
            for w in workers:
                try:
                    resp = await w.project_info(uri=request.uri)
                    yield api_pb2.ProjectInfo(
                        status=resp.status.name,
                        uri=resp.uri,
                        filename=resp.filename,
                        crs=resp.crs,
                        last_modified=_to_iso8601(datetime.fromtimestamp(resp.last_modified)),
                        storage=resp.storage,
                        has_bad_layers=resp.has_bad_layers,
                        layers=[_layer(layer) for layer in resp.layers],
                        cache_id=resp.cache_id,
                    )
                except WorkerError as err:
                    # Catch 404 errors
                    if err.code != 404:
                        raise

    #
    # Plugin list
    #
    async def ListPlugins(
        self,
        request: api_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.PluginInfo, None, None]:

        count, plugins = self._pool.list_plugins()
        await context.send_initial_metadata([("x-reply-header-installed-plugins", str(count))])
        for item in plugins:
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
            retval = self._pool.dump_config()
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

        try:
            await self._pool.update_config(obj)
            return api_pb2.Empty()
        except WorkerError as e:
            await _abort_on_error(context, e.status, e.details, "SetConfig")
        except Exception as err:
            logger.critical(traceback.format_exc())
            await _abort_on_error(context, 500, str(err), "SetConfig")

    #
    # Get Env Status
    #

    async def GetEnv(
        self,
        request: api_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.JsonConfig, None, None]:

        try:
            return api_pb2.JsonConfig(json=json.dumps(self._pool.env))
        except WorkerError as e:
            await _abort_on_error(context, e.status, e.details, "GetEnv")
        except Exception as err:
            logger.critical(traceback.format_exc())
            await _abort_on_error(context, 500, str(err), "GetEnv")

    #
    # Stats
    #

    async def Stats(
        self,
        request: api_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.StatsReply:
        # Server serving status
        return api_pb2.StatsReply(
            num_workers=self._pool.num_workers,
            stopped_workers=self._pool.stopped_workers,
            worker_failure_pressure=self._pool.worker_failure_pressure,
            request_pressure=self._pool.request_pressure,
            uptime=int(time() - self._pool.start_time)
        )


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
        cache_id=resp.cache_id,
    )
