
from time import time
from typing import (
    Awaitable,
    Callable,
    Dict,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    TypeAlias,
)
from urllib.parse import urlencode

from aiohttp import web

from qjazz_contrib.core import logger
from qjazz_rpcw._grpc import qjazz_pb2

from . import metrics
from .channel import Channel
from .webutils import CORSHandler, _decode, public_location, public_url

#
# Qgis request Handlers
#


class RpcMetadataProtocol(Protocol):
    def trailing_metadata(self) -> Awaitable[Sequence[Tuple[str, str]]]: ...


MetricCollector: TypeAlias = Callable[
    [
        web.Request,
        Channel,
        metrics.Data,
    ],
    Awaitable,
]


def get_response_headers(metadata: Sequence[Tuple[str, str]]) -> Tuple[int, Mapping[str, str]]:
    """ write response headers and return
        status code
    """
    status_code = 200
    headers = {}

    for k, v in metadata:
        match k:
            case "x-reply-status-code":
                status_code = int(v)
            case n if n.startswith("x-reply-header-"):
                headers[n.removeprefix("x-reply-header-")] = v

    return status_code, headers


def get_metadata(request: web.Request, channel: Channel) -> Sequence[Tuple[str, str]]:
    return channel.get_metadata(
        (k.lower(), v) for k, v in request.headers.items()
    )


def on_unknown_rpc_error(metadata: Sequence[Tuple[str, str]], details: str):
    """ Handle rpc error which is out
        of gRPC namespace.
        Usually occurs when a non-Qgis error
        is raised before reaching qgis server.
        In this case return the error code found in
        the trailing metadata.
    """
    code, headers = get_response_headers(metadata)

    class _HTTPError(web.HTTPError):
        status_code = code

    raise _HTTPError(
        reason="Backend error",
        text=details,
        headers=headers,
    )


async def collect_metrics(
    collect: MetricCollector,
    http_req: web.Request,
    channel: Channel,
    start: float,
    project: str | None,
    service: str,
    request: str,
    status_code: int,
):
    """ Emit metrics
    """
    project = project
    latency = int((time() - start) * 1000.)
    await collect(
        http_req,
        channel,
        metrics.Data(
            status=status_code,
            service=service,
            request=request,
            project=project,
            response_time=latency,
         ),
    )


#
# OWS
#


ALLOW_OWS_HEADERS = (
    "X-Qgis-Service-Url, "
    "X-Qgis-WMS-Service-Url, "
    "X-Qgis-WFS-Service-Url, "
    "X-Qgis-WCS-Service-Url, "
    "X-Qgis-WMTS-Service-Url, "
    # Required if the request has an "Authorization" header.
    # This is useful to implement authentification on top QGIS SERVER
    # see https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Access-Control-Allow-Headers &
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Authorization
    "Authorization"
)

ALLOW_OWS_METHODS = "POST, GET, HEAD, OPTIONS"


def check_getfeature_limit(channel: Channel, arguments: Dict[str, str]) -> Dict[str, str]:
    """ Take care of WFS/GetFeature limit

        Qgis does not set a default limit and unlimited
        request may cause issues
    """
    limit = channel.getfeature_limit
    if limit \
        and arguments.get('SERVICE', '').upper() == 'WFS' \
        and arguments.get('REQUEST', '').lower() == 'getfeature':

        if arguments.get('VERSION', '').startswith('2.'):
            key = 'COUNT'
        else:
            key = 'MAXFEATURES'

        try:
            actual_limit = int(arguments.get(key, 0))
            if actual_limit > 0:
                limit = min(limit, actual_limit)
        except ValueError:
            pass
        arguments[key] = str(limit)

    return arguments


async def ows_handler(
    request: web.Request,
    *,
    channel: Channel,
    cors_options_handler: CORSHandler,
    project: Optional[str] = None,
    collect: Optional[MetricCollector] = None,
) -> web.StreamResponse:

    if request.method == 'OPTIONS':
        return await cors_options_handler(
            request,
            allow_methods=ALLOW_OWS_METHODS,
            allow_headers=ALLOW_OWS_HEADERS,
        )

    arguments = await get_ows_arguments(request)

    ows_service = arguments.pop('SERVICE', "")
    ows_request = arguments.pop('REQUEST', "")
    ows_version = arguments.pop('VERSION', "")

    arguments = check_getfeature_limit(channel, arguments)

    if collect:
        start = time()

    url = public_location(request)
    metadata = get_metadata(request, channel)

    try:
        async with channel.stub(on_unknown_rpc_error) as stub:
            stream = stub.ExecuteOwsRequest(
                qjazz_pb2.OwsRequest(
                    service=ows_service,
                    request=ows_request,
                    version=ows_version,
                    target=project,
                    url=url,
                    direct=channel.allow_direct_resolution,
                    options=urlencode(arguments),
                    request_id=request.get('request_id', ''),
                    method=request.method,
                    body=await request.read() if request.has_body else None,
                    content_type=request.content_type,
                ),
                metadata=metadata,
                timeout=channel.timeout,
            )

            status, headers = get_response_headers(await stream.initial_metadata())
            response = web.StreamResponse(status=status, headers=headers)
            # XXX: Get the first chunk before preparing the request
            # so we trigger the grcp error.
            # Otherwise this will send an invalid chunked response
            streamit = aiter(stream)
            try:
                chunk = await anext(streamit)
            except StopAsyncIteration:
                # Nodata
                stream.cancel()
                return web.Response(status=status, headers=headers)

            try:
                await response.prepare(request)
                await response.write(chunk.chunk)
                async for chunk in streamit:
                    await response.write(chunk.chunk)
                await response.write_eof()
                return response
            except OSError as err:
                stream.cancel()
                logger.error("Connection cancelled: %s", err)
                raise

    except web.HTTPException as exc:
        status = exc.status
        raise
    finally:
        if collect:
            await collect_metrics(
                collect,
                request,
                channel,
                start,
                project,
                ows_service,
                ows_request,
                status_code=status,
            )


async def get_ows_arguments(request: web.Request) -> Dict[str, str]:
    """ Retrieve argument either from body if GET method or
        from body
    """
    args: Mapping
    if request.method == 'GET':
        args = request.query
    elif request.method == 'POST' and (\
        request.content_type.startswith('application/x-www-form-urlencoded') or \
        request.content_type.startswith('multipart/form-data') \
    ):
        args = await request.post()
    else:
        args = request.query

    return {k.upper(): _decode(k, v) for k, v in args.items() if isinstance(v, str)}

#
# API
#


ALLOW_API_METHODS = "GET, POST, PUT, HEAD, PATCH, OPTIONS"
ALLOW_API_HEADERS = "Authorization"


async def api_handler(
    request: web.Request,
    *,
    channel: Channel,
    api: str,
    path: str,
    cors_options_handler: CORSHandler,
    project: Optional[str] = None,
    collect: Optional[MetricCollector] = None,
    delegate: bool = False,
) -> web.StreamResponse:

    if request.method == 'OPTIONS':
        return await cors_options_handler(
            request,
            allow_methods=ALLOW_API_METHODS,
            allow_headers=ALLOW_API_HEADERS,
        )

    if collect:
        start = time()

    # !IMPORTANT set the root url without the api path
    url = public_url(request, request.path.removesuffix(path))
    metadata = get_metadata(request, channel)

    try:
        async with channel.stub(on_unknown_rpc_error) as stub:
            stream = stub.ExecuteApiRequest(
                qjazz_pb2.ApiRequest(
                    name=api,
                    path=path,
                    method=request.method,
                    data=await request.read() if request.has_body else None,
                    delegate=delegate,
                    target=project,
                    url=url,
                    direct=channel.allow_direct_resolution,
                    options=request.query_string,
                    request_id=request.get('request_id', ''),
                    content_type=request.content_type,
                ),
                metadata=metadata,
                timeout=channel.timeout,
            )

            status, headers = get_response_headers(await stream.initial_metadata())

            if request.method == 'HEAD':
                stream.cancel()
                return web.Response(status=status, headers=headers)

            # See above
            streamit = aiter(stream)
            try:
                chunk = await anext(streamit)
            except StopAsyncIteration:
                # Nodata
                stream.cancel()
                return web.Response(status=status, headers=headers)

            try:
                response = web.StreamResponse(status=status, headers=headers)
                await response.prepare(request)
                await response.write(chunk.chunk)
                async for chunk in streamit:
                    await response.write(chunk.chunk)
                await response.write_eof()
                return response
            except OSError as err:
                stream.cancel()
                logger.error("Connection cancelled: %s", err)
                raise

    except web.HTTPException as exc:
        status = exc.status
        raise
    finally:
        if collect:
            await collect_metrics(
                collect,
                request,
                channel,
                start,
                project,
                api,
                path,
                status_code=status,
            )
