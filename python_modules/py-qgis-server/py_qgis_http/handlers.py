
from time import time
from urllib.parse import urlencode

from aiohttp import web
from typing_extensions import (
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

from py_qgis_contrib.core import logger
from py_qgis_rpc._grpc import api_pb2

from . import metrics
from .channel import Channel
from .webutils import CORSHandler, _decode, public_location, public_url

#
# Qgis request Handlers
#

ReportType: TypeAlias = Tuple[Optional[int], int, Optional[int]]


class RpcMetadataProtocol(Protocol):
    def trailing_metadata(self) -> Awaitable[Sequence[Tuple[str, str]]]: ...


# debug report
async def get_report(stream: RpcMetadataProtocol) -> ReportType:  # ANN001
    """ Return debug report from trailing_metadata
    """
    md = await stream.trailing_metadata()
    memory, duration, timestamp = None, 0, None
    for k, v in md:
        match k:
            case 'x-debug-memory':
                memory = int(v)
            case 'x-debug-duration':
                duration = int(float(v) * 1000.0)
    return (memory, duration, timestamp)


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


def on_unknown_rpc_error(metadata: Sequence[Tuple[str, str]]):
    """ Handle rpc error which is out
        of gRPC namespace.
        Usually occurs when a non-Qgis error
        is raised before reaching qgis server.
        In this case return the error code found in
        the initial metadata.
    """
    status_code, headers = get_response_headers(metadata)

    class _HTTPException(web.HTTPException):
        status_code = status_code

    raise _HTTPException(
        reason="Service backend exception",
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
    report: ReportType | None,
    cached: bool,
):
    """ Emit metrics
    """
    if not report:
        logger.error("Something prevented to get metric's report...")
        return

    project = project
    latency = int((time() - start) * 1000.)
    memory, duration, _ = report
    latency -= duration
    await collect(
        http_req,
        channel,
        metrics.Data(
            status=status_code,
            service=service,
            request=request,
            project=project,
            memory_footprint=memory,
            response_time=duration,
            latency=latency,
            cached=cached,
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

    report_data: Optional[ReportType] = None
    if collect:
        start = time()

    url = public_location(request)
    metadata = get_metadata(request, channel)

    try:
        async with channel.stub(on_unknown_rpc_error) as stub:
            stream = stub.ExecuteOwsRequest(
                api_pb2.OwsRequest(
                    service=ows_service,
                    request=ows_request,
                    version=ows_version,
                    target=project,
                    url=url,
                    direct=channel.allow_direct_resolution,
                    options=urlencode(check_getfeature_limit(channel, arguments)),
                    request_id=request.get('request_id', ''),
                    debug_report=collect is not None,
                ),
                metadata=metadata,
                timeout=channel.timeout,
            )

            status, headers = get_response_headers(await stream.initial_metadata())
            response = web.StreamResponse(status=status, headers=headers)
            # XXX: Get the first chunk before preparing the request
            # so we trigger the grcp error.
            # Otherwise this will send an invalid chunked responsea
            streamit = aiter(stream)
            chunk = await anext(streamit)
            await response.prepare(request)

            try:
                await response.write(chunk.chunk)
                async for chunk in streamit:
                    await response.write(chunk.chunk)
            except OSError as err:
                stream.cancel()
                logger.error("Connection cancelled: %s", err)
                raise

            await response.write_eof()

            if collect:
                report_data = await get_report(stream)

            return response

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
                report=report_data,
                cached=request.headers.get('X-Qgis-Cache') == 'HIT',
            )


async def get_ows_arguments(request: web.Request) -> Dict[str, str]:
    """ Retrieve argument either from body if GET method or
        from body
    """
    args: Mapping
    if request.method == 'GET':
        args = request.query
    elif request.content_type.startswith('application/x-www-form-urlencoded') or \
         request.content_type.startswith('multipart/form-data'):
        args = await request.post()

    return {k.upper(): _decode(k, v) for k, v in args.items()}

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

    report_data: Optional[ReportType] = None
    if collect:
        start = time()

    # !IMPORTANT set the root url without the api path
    url = public_url(request, request.path.removesuffix(path))
    metadata = get_metadata(request, channel)

    try:
        async with channel.stub(on_unknown_rpc_error) as stub:
            stream = stub.ExecuteApiRequest(
                api_pb2.ApiRequest(
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
                    debug_report=collect is not None,
                ),
                metadata=metadata,
                timeout=channel.timeout,
            )

            status, headers = get_response_headers(await stream.initial_metadata())
            response = web.StreamResponse(status=status, headers=headers)

            if request.method == 'HEAD':
                stream.cancel()
                await response.write_eof()
                return response

            # See above
            streamit = aiter(stream)
            chunk = await anext(streamit)
            await response.prepare(request)

            try:
                await response.write(chunk.chunk)
                async for chunk in streamit:
                    await response.write(chunk.chunk)
            except OSError as err:
                stream.cancel()
                logger.error("Connection cancelled: %s", err)
                raise

            await response.write_eof()

            if collect:
                report_data = await get_report(stream)

            return response
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
                report=report_data,
                cached=request.headers.get('X-Qgis-Cache') == 'HIT',
            )
