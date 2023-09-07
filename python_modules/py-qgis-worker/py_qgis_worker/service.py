import grpc
from ._grpc import api_pb2
from ._grpc import api_pb2_grpc

from datetime import datetime, timezone
from typing import (
    Generator,
    Tuple,
    Any,
    Iterable,
)

import traceback

from py_qgis_contrib.core import logger

from . import messages as _m


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


async def _abort_on_fail(context: grpc.aio.ServicerContext, code: int):
    await context.send_initial_metadata(
        [('x-reply-status-code', str(code))]
    )
    raise ExecError


async def _abort_on_error(context: grpc.aio.ServicerContext, code: int, details: str):
    await context.abort(_match_grpc_code(code), details)


class ExecError(Exception):
    pass


class RpcService(api_pb2_grpc.QgisWorkerServicer):
    """ Worker API
    """

    def __init__(self, worker):
        super().__init__()
        self._worker = worker

    async def Ping(
        self,
        request: api_pb2.PingRequest,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.PingReply:
        """  Simple ping request
        """
        echo = request.echo

        return api_pb2.PingReply(echo=echo)

    #
    # OWS request
    #
    async def ExecuteOwsRequest(
        self,
        request: api_pb2.OwsRequest,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.ResponseChunk, None, None]:

        try:
            headers = dict(context.invocation_metadata())

            status, resp = await self._worker.io.send_message(
                _m.OWSRequest(
                    service=request.service,
                    request=request.request,
                    version=request.version,
                    options=request.options,
                    target=request.target,
                    url=request.url,
                    direct=request.direct,
                    headers=headers,
                ),
            )

            # Request failed before reaching Qgis server
            if status != 200:
                await _abort_on_fail(context, status)

            # Send Headers
            metadata = list(_headers_to_metadata(resp.headers.items()))
            metadata.append(('x-reply-status-code', str(resp.status_code)))
            await context.send_initial_metadata(metadata)

            # Send data
            yield api_pb2.ResponseChunk(chunk=resp.data)

            if resp.chunked:
                async for chunk in self._worker.io.stream_bytes():
                    yield api_pb2.ResponseChunk(chunk=chunk)

            # Final report
            _ = await self._worker.io.read()

        except ExecError:
            await _abort_on_error(context, status, resp)
        except Exception as err:
            logger.critical(traceback.format_exc())
            await _abort_on_error(context, 500, str(err))
    #
    # Generic request
    #

    async def ExecuteRequest(
        self,
        request: api_pb2.GenericRequest,
        context: grpc.aio.ServicerContext,
    ) -> Generator[api_pb2.ResponseChunk, None, None]:

        try:
            headers = dict(context.invocation_metadata())

            try:
                http_method = _m.HTTPMethod[request.method]
            except KeyError:
                status = 405
                resp = f"Invalid method {request.method}"
                raise ExecError

            status, resp = await self._worker.io.send_message(
                _m.Request(
                    url=request.url,
                    method=http_method,
                    data=request.data,
                    target=request.target,
                    direct=request.direct,
                    headers=headers,
                ),
            )
            # Request failed before reaching Qgis server
            if status != 200:
                _abort_on_fail(context, status)

            # Send Headers
            metadata = list(_headers_to_metadata(resp.headers.items()))
            metadata.append(('x-reply-status-code', str(resp.status_code)))
            await context.send_initial_metadata(metadata)

            # Send data
            yield api_pb2.ResponseChunk(chunk=resp.data)

            if resp.chunked:
                async for chunk in self._worker.io.stream_bytes():
                    yield api_pb2.ResponseChunk(chunk=chunk)

            # Final report
            _ = await self._worker.io.read()

        except ExecError:
            await _abort_on_error(context, status, resp)
        except Exception as err:
            logger.critical(traceback.format_exc())
            await _abort_on_error(context, 500, str(err))

    #
    # Pull project
    #
    async def PullProject(
        self,
        request: api_pb2.PullRequest,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.CacheInfo:

        try:
            status, resp = await self._worker.io.send_message(
                _m.PullProject(uri=request.uri)
            )

            if status != 200:
                await _abort_on_fail(context, status)

            if resp.last_modified:
                last_modified = _to_iso8601(datetime.fromtimestamp(resp.last_modified))
            else:
                last_modified = ""

            return api_pb2.CacheInfo(
                uri=resp.uri,
                status=resp.status.name,
                name=resp.name,
                storage=resp.storage,
                last_modified=last_modified,
                saved_version=resp.saved_version or "",
                debug_metadata=resp.debug_metadata,
            )

        except ExecError:
            await _abort_on_error(context, status, resp)
        except Exception as err:
            logger.critical(traceback.format_exc())
            await _abort_on_error(context, 500, str(err))
