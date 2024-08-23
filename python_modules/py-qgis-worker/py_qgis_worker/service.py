import json
import os
import traceback

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from time import time
from typing import AsyncGenerator, AsyncIterator, Iterable, Iterator, Tuple

import grpc

from grpc_health.v1 import health_pb2
from grpc_health.v1._async import HealthServicer

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import ConfigError, confservice, read_config_toml
from py_qgis_contrib.core.utils import to_iso8601

from . import messages as _m
from ._grpc import api_pb2, api_pb2_grpc
from .config import ENV_CONFIGFILE, RemoteConfigError
from .pool import Worker, WorkerError, WorkerPool
from .restore import Restore

#
# https://grpc.github.io/grpc/python/
#


def _match_grpc_code(code: int) -> grpc.StatusCode:
    match code:
        case 400:
            return grpc.StatusCode.INVALID_ARGUMENT
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


def _headers_to_metadata(coll: Iterable[Tuple[str, str]]) -> Iterator[Tuple[str, str]]:
    return ((f"x-reply-header-{k.lower()}", str(v)) for k, v in coll)


async def _abort_on_error(
    context: grpc.aio.ServicerContext,
    code: int,
    details: str,
    request: str,
):
    logger.log_req("%s\t%s\t%s", code, request, details)
    await context.send_initial_metadata(
        [('x-reply-status-code', str(code))],
    )
    await context.abort(_match_grpc_code(code), details)


class WorkerMixIn:

    # Hint for mypy that attribute is expected to exists
    _pool: WorkerPool

    @asynccontextmanager
    async def get_worker(
        self,
        context: grpc.aio.ServicerContext,
        request: str,
    ) -> AsyncGenerator[Worker, None]:
        try:
            async with self._pool.get_worker() as worker:
                yield worker
        except WorkerError as e:
            await _abort_on_error(context, e.code, e.details, request)

    @asynccontextmanager
    async def wait_for_all_workers(
        self,
        context: grpc.aio.ServicerContext,
        request: str,
    ) -> AsyncGenerator[Iterator[Worker], None]:
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
    ) -> AsyncIterator[api_pb2.ResponseChunk]:

        if request.request_id:
            logger.log_rreq(
                "OWS\t%s\t%s\t%s\tREQ-ID:%s",
                request.service,
                request.request,
                request.target,
                request.request_id,
            )

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
                context.set_trailing_metadata([
                    ('x-debug-memory', str(report.memory)),
                    ('x-debug-duration', str(report.duration)),
                    ('x-debug-timestamp', str(report.timestamp)),
                ])

            _t_end = time()
            logger.log_req(
                "OWS\t%s\t%s\t%s\t%d\t%d%s",
                request.service,
                request.request,
                request.target,
                size,
                int((_t_end - _t_start) * 1000.),
                f"\tREQ-ID:{request.request_id}" if request.request_id else "",
            )

    #
    # API request
    #
    async def ExecuteApiRequest(
        self,
        request: api_pb2.ApiRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[api_pb2.ResponseChunk]:

        if request.request_id:
            logger.log_rreq(
                "API\t%s\t%s\t%s\tREQ-ID:%s",
                request.name,
                request.url,
                request.target,
                request.request_id,
            )

        async with self.get_worker(context, "ExecuteOwsRequest") as worker:
            headers = dict(context.invocation_metadata())

            _t_start = time()

            try:
                http_method = _m.HTTPMethod[request.method]
            except KeyError:
                details = f"Invalid method {request.method}"
                await _abort_on_error(context, 405, details, "ExecuteApiRequest")

            resp, stream = await worker.api_request(
                name=request.name,
                path=request.path,
                method=http_method,
                data=request.data,
                delegate=request.delegate,
                target=request.target,
                url=request.url,
                direct=request.direct,
                options=request.options,
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
                context.set_trailing_metadata([
                    ('x-debug-memory', str(report.memory)),
                    ('x-debug-duration', str(report.duration)),
                    ('x-debug-timestamp', str(report.timestamp)),
                ])

            _t_end = time()
            logger.log_req(
                "API\t%s\t%s\t%s\t%d\t%d%s",
                request.name,
                request.url,
                request.target,
                size,
                int((_t_end - _t_start) * 1000.),
                f"\tREQ-ID:{request.request_id}" if request.request_id else "",
            )

    #
    # Generic request
    #

    async def ExecuteRequest(
        self,
        request: api_pb2.GenericRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[api_pb2.ResponseChunk]:

        if request.request_id:
            logger.log_req(
                "---\t%s\t%s\tREQ-ID:%s",
                request.url,
                request.target,
                request.request_id,
            )

        async with self.get_worker(context, "ExecuteRequest") as worker:
            headers = dict(context.invocation_metadata())

            _t_start = time()

            try:
                http_method = _m.HTTPMethod[request.method]
            except KeyError:
                details = f"Invalid method {request.method}"
                await _abort_on_error(context, 405, details, "ExecuteRequest")

            resp, stream = await worker.request(
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

            chunk = resp.data
            size = len(chunk)

            # Send data
            yield api_pb2.ResponseChunk(chunk)
            if stream:
                async for chunk in stream:
                    size += len(chunk)
                    yield api_pb2.ResponseChunk(chunk=chunk)

            # Final report
            if request.debug_report:
                report = await worker.io.read()
                context.set_trailing_metadata([
                    ('x-debug-memory', str(report.memory)),
                    ('x-debug-duration', str(report.duration)),
                    ('x-debug-timestamp', str(report.timestamp)),
                ])

            _t_end = time()
            logger.log_req(
                "---\t%s\t%s\t%d\t%d%s",
                request.url,
                request.target,
                size,
                int((_t_end - _t_start) * 1000.),
                f"\tREQ-ID:{request.request_id}" if request.request_id else "",
            )


# ======================
# Admin service
# ======================

class QgisAdmin(api_pb2_grpc.QgisAdminServicer, WorkerMixIn):

    def __init__(
        self,
        pool: WorkerPool,
        health_servicer: HealthServicer,
        restore: Restore,
    ):
        super().__init__()
        self._pool = pool
        self._health_servicer = health_servicer
        self._restore = restore

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
        """ Set the Healthcheck service
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
            ServingStatus.Name(status),
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
    ) -> AsyncIterator[api_pb2.CacheInfo]:

        async with self.wait_for_all_workers(context, "CheckoutProject") as workers:
            for w in workers:
                resp = await w.checkout_project(
                    uri=request.uri,
                    pull=request.pull,
                )
                yield _new_cache_info(resp)

                if request.pull:
                    self._restore.update(resp)

    #
    # Pull projects
    #
    async def PullProjects(
        self,
        requests: AsyncIterator[api_pb2.ProjectRequest],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[api_pb2.CacheInfo]:

        async with self.wait_for_all_workers(context, "PullProjects") as workers:
            async for req in requests:
                for w in workers:
                    resp = await w.checkout_project(uri=req.uri, pull=True)
                yield _new_cache_info(resp)

                self._restore.update(resp)

    #
    # Drop project
    #
    async def DropProject(
        self,
        request: api_pb2.CheckoutRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[api_pb2.CacheInfo]:

        async with self.wait_for_all_workers(context, "DropProject") as workers:
            for w in workers:
                resp = await w.drop_project(uri=request.uri)
                yield _new_cache_info(resp)

                self._restore.update(resp)
    #
    # Cache list
    #

    async def ListCache(
        self,
        request: api_pb2.ListRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[api_pb2.CacheInfo]:
        """ Sent cache list from all workers
        """
        try:
            status_filter = _m.CheckoutStatus[request.status_filter]
        except KeyError:
            status_filter = None

        async with self.wait_for_all_workers(context, "ListCache") as workers:
            count = 0
            cachelist: Tuple[AsyncIterator[_m.CacheInfo], ...] = tuple()
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

            self._restore.clear()

            return api_pb2.Empty()

    #
    # Update cache
    #
    async def UpdateCache(
        self,
        request: api_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[api_pb2.CacheInfo]:
        """ Update and synchronize all Worker's cache
        """
        async with self.wait_for_all_workers(context, "UpdateCache") as workers:
            _workers = list(workers)
            _all = set()
            for w in _workers:
                # Collect all items for all workers
                _, items = await w.list_cache()
                if items:
                    async for item in items:
                        _all.add(item.uri)
            for uri in _all:
                # Update all items for all workers
                for w in _workers:
                    yield _new_cache_info(await w.checkout_project(uri, pull=True))

    #
    # List Catalog Items
    #
    async def Catalog(
        self,
        request: api_pb2.CatalogRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[api_pb2.CatalogItem]:

        async with self.get_worker(context, "Catalog") as worker:
            items = await worker.catalog(location=request.location)
            async for item in items:
                yield api_pb2.CatalogItem(
                    uri=item.uri,
                    name=item.name,
                    storage=item.storage,
                    last_modified=to_iso8601(datetime.fromtimestamp(item.last_modified)),
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

        async with self.wait_for_all_workers(context, "GetProjectInfo") as workers:
            for w in workers:
                try:
                    resp = await w.project_info(uri=request.uri)
                    return api_pb2.ProjectInfo(
                        status=resp.status.name,
                        uri=resp.uri,
                        filename=resp.filename,
                        crs=resp.crs,
                        last_modified=to_iso8601(datetime.fromtimestamp(resp.last_modified)),
                        storage=resp.storage,
                        has_bad_layers=resp.has_bad_layers,
                        layers=[_layer(layer) for layer in resp.layers],
                        cache_id=resp.cache_id,
                    )
                except WorkerError as err:
                    # Catch 404 errors
                    if err.code != 404:
                        raise
            # No project found: raise a 404 errors
            raise WorkerError(404, f"Project {request.uri} not found")

    #
    # Plugin list
    #
    async def ListPlugins(
        self,
        request: api_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[api_pb2.PluginInfo]:

        count, plugins = self._pool.list_plugins()
        await context.send_initial_metadata([("x-reply-header-installed-plugins", str(count))])
        if plugins:
            for item in plugins:
                yield api_pb2.PluginInfo(
                    name=item.name,
                    path=str(item.path),
                    plugin_type=item.plugin_type.name,
                    metadata=json.dumps(item.metadata),
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
            rv = self._pool.config_dump_json()
        except WorkerError as e:
            await _abort_on_error(context, e.code, e.details, "GetConfig")
        except Exception as err:
            logger.critical(traceback.format_exc())
            await _abort_on_error(context, 500, str(err), "GetConfig")

        return api_pb2.JsonConfig(json=rv)

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
            confservice.update_config(obj)
        except ConfigError as err:
            await _abort_on_error(context, 400, err.json(include_url=False), "SetConfig")

        logger.trace("Updating workers with configuration\n %s", obj)

        try:
            await self._pool.update_config(confservice.conf.worker)
        except WorkerError as e:
            await _abort_on_error(context, e.code, e.details, "SetConfig")
        except Exception as err:
            logger.critical(traceback.format_exc())
            await _abort_on_error(context, 500, str(err), "SetConfig")

        return api_pb2.Empty()

    #
    # Reload config
    #
    async def ReloadConfig(
        self,
        request: api_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.Empty:

        try:
            # If remote url is defined, load configuration
            # from it
            if confservice.conf.config_url.is_set():
                obj = await confservice.conf.config_url.load_configuration()
            elif ENV_CONFIGFILE in os.environ:
                # Fallback to configfile (if any)
                configpath = Path(os.environ[ENV_CONFIGFILE])
                logger.info("** Reloading config from %s **", configpath)
                obj = read_config_toml(
                    configpath,
                    location=str(configpath.parent.absolute()),
                )
            else:
                obj = {}

            await self._pool.update_config(obj)
        except RemoteConfigError as err:
            await _abort_on_error(context, 502, str(err), "Reload")
        except WorkerError as e:
            await _abort_on_error(context, e.code, e.details, "ReloadConfig")
        except Exception as err:
            logger.critical(traceback.format_exc())
            await _abort_on_error(context, 500, str(err), "Reload")

        return api_pb2.Empty()

    #
    # Get Env Status
    #
    async def GetEnv(
        self,
        request: api_pb2.Empty,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.JsonConfig:

        try:
            rv = api_pb2.JsonConfig(json=json.dumps(self._pool.env))
        except WorkerError as e:
            await _abort_on_error(context, e.code, e.details, "GetEnv")
        except Exception as err:
            logger.critical(traceback.format_exc())
            await _abort_on_error(context, 500, str(err), "GetEnv")
        # Make mypy happy with return statement since it does not knows
        # that _abort_on_error actually raise an exception.
        return rv

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
            uptime=int(time() - self._pool.start_time),
        )


#
# Build a cache info from response
#
def _new_cache_info(resp: _m.CacheInfo) -> api_pb2.CacheInfo:

    last_modified = to_iso8601(
        datetime.fromtimestamp(resp.last_modified),
    ) if resp.last_modified else ""

    timestamp = int(resp.timestamp) if resp.timestamp else -1

    return api_pb2.CacheInfo(
        uri=resp.uri,
        status=resp.status.name,
        in_cache=resp.in_cache,
        timestamp=timestamp,
        name=resp.name,
        storage=resp.storage,
        last_modified=last_modified,
        saved_version=resp.saved_version or "",
        debug_metadata=resp.debug_metadata,
        cache_id=resp.cache_id,
        last_hit=int(resp.last_hit),
        hits=resp.hits,
        pinned=resp.pinned,
    )
