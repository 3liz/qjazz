import asyncio
import signal
import traceback

from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import PurePosixPath

from aiohttp import web
from aiohttp.abc import AbstractAccessLogger
from typing_extensions import (
    AsyncGenerator,
    Awaitable,
    Callable,
    Optional,
    TypeAlias,
    no_type_check,
)

from py_qgis_contrib.core import logger

from . import metrics
from .admin import (
    admin_root,
    backends_list_route,
    backends_route,
    config_route,
)
from .channels import Channels
from .config import (
    AdminHttpConfig,
    ConfigProto,
    HttpConfig,
    HttpCORS,
    MetricsConfig,
)
from .handlers import api_handler, ows_handler
from .models import ErrorResponse
from .router import RouterConfig

try:
    __version__ = version('py_qgis_http')
except PackageNotFoundError:
    __version__ = "dev"

SERVER_HEADER = f"Py-Qgis-Http-Server2 {__version__}"

#
# Logging
#


REQ_FORMAT = (
    "{ip}\t{code}\t{method}\t{url}\t{time}\t{length}"
    "\t{agent}\t{referer}"
)
REQ_ID_FORMAT = "REQ-ID:{request_id}"
RREQ_FORMAT = "{ip}\t{method}\t{url}\t{agent}\t{referer}\t" + REQ_ID_FORMAT


class AccessLogger(AbstractAccessLogger):
    """ Custom access logger
    """

    def log(self, request: web.BaseRequest, response: web.StreamResponse, duration: float):

        agent = request.headers.get('User-Agent', "")
        referer = request.headers.get('Referer', "")

        fmt = REQ_FORMAT.format(
            ip=request.remote,
            method=request.method,
            url=request.rel_url,
            code=response.status,
            time=int(1000.0 * duration),
            length=response.content_length or -1,
            referer=referer,
            agent=agent,
        )

        # See https://docs.aiohttp.org/en/stable/web_advanced.html#request-s-storage
        request_id = request.get('request_id')
        if request_id:
            fmt += f"\t{REQ_ID_FORMAT.format(request_id=request_id)}"

        logger.log_req(fmt)


#
# CORS
#

async def cors_options_handler(
    request: web.Request,
    allow_methods: str,
    allow_headers: str,
) -> web.Response:
    """  Set correct headers for 'OPTIONS' method
    """
    allow_methods = allow_methods
    headers = {
        "Allow":  allow_methods,
        "Access-Control-Allow-Headers": allow_headers,
    }
    if request.headers.get('Origin'):
        # Required in CORS context
        # see https://developer.mozilla.org/fr/docs/Web/HTTP/M%C3%A9thode/OPTIONS
        headers['Access-Control-Allow-Methods'] = allow_methods

    return web.Response(headers=headers)


def set_access_control_headers(
    mode: HttpCORS,
) -> Callable[[web.Request, web.StreamResponse], Awaitable[None]]:
    """ Build a response prepare callback
    """
    async def set_access_control_headers_(
        request: web.Request,
        response: web.StreamResponse,
    ):
        """  Handle Access control and cross origin headers (CORS)
        """
        origin = request.headers.get('Origin')
        if origin:
            match mode:
                case 'all':
                    allow_origin = '*'
                case 'same-origin':
                    allow_origin = origin
                    response.headers['Vary'] = 'Origin'
                case _ as url:
                    allow_origin = str(url)

            response.headers['Access-Control-Allow-Origin'] = allow_origin

    return set_access_control_headers_  # typing: ignore [return-value]


#
#  Headers
#

async def set_server_headers(request: web.Request, response: web.StreamResponse):
    """ Set server headers
    """
    response.headers['Server'] = SERVER_HEADER

    request_id = request.get('request_id')
    if request_id:
        response.headers['X-Request-ID'] = request_id


#
# Incoming request logger
#

@web.middleware
async def log_incoming_request(request, handler):
    request_id = request.headers.get('X-Request-ID', "")
    if request_id:
        request['request_id'] = request_id

        agent = request.headers.get('User-Agent', "")
        referer = request.headers.get('Referer', "")

        fmt = RREQ_FORMAT.format(
            ip=request.remote,
            method=request.method,
            url=request.rel_url,
            referer=referer,
            agent=agent,
            request_id=request.get('request_id', ""),
        )

        logger.log_rreq(fmt)

    return await handler(request)


#
# Unhandled exceptions
#

@web.middleware
async def unhandled_exceptions(request, handler):
    try:
        return await handler(request)
    except web.HTTPException as e:
        logger.debug("Exception: %s: %s", e, e.headers)
        if not e.content_type.startswith('application/json'):
            e.content_type = "application/json"
            e.text = ErrorResponse(message=e.reason).model_dump_json()
        raise
    except Exception:
        logger.critical(f"Error handling request:\n{traceback.format_exc()}")
        raise web.HTTPInternalServerError(
            content_type="application/json",
            text=ErrorResponse(
                message="Internal server error",
            ).model_dump_json(),
        ) from None


#
# Router
#

def redirect(path: str) -> Callable[[web.Request], Awaitable]:
    async def _redirect(request):
        raise web.HTTPFound(path)
    return _redirect


class _Router:

    def __init__(self, channels: Channels, conf: RouterConfig):
        self.channels = channels

        self._collect: Optional[Callable] = None

        # Set router
        self._channels_last_modified = 0.
        self._router = conf.create_instance()
        self._update_routes()

    async def set_metrics(self, metrics_conf: MetricsConfig) -> metrics.Metrics:
        """ Initialize metrics service
        """
        metrics_service = metrics_conf.create_instance()
        self._collect = metrics_service.emit
        return metrics_service

    def _update_routes(self) -> None:
        """ Update routes and routable class
        """
        if not self.channels.is_modified_since(self._channels_last_modified):
            return

        self._channels_last_modified = self.channels.last_modified

        logger.debug("Updating backend's routes")
        routes = {chan.route: chan for chan in self.channels.backends}

        @dataclass
        class _Routable:
            request: web.Request

            def get_route(self) -> Optional[str]:  # type: ignore
                """
                Return a route (str) for the
                current request path.
                """
                path = PurePosixPath(self.request.path)
                for route in routes:
                    if path.is_relative_to(route):
                        return route

                logger.error("No routes found for %s", path)

        self._routes = routes
        self._routable_class = _Routable

    async def do_route(self, request: web.Request) -> web.StreamResponse:
        """ Override

            Ask inner router to return a `Route` object
        """
        # Update routes if required
        # XXX use event or barrier
        self._update_routes()

        route = await self._router.route(self._routable_class(request=request))
        logger.trace("Route %s found for %s", route, request.url)
        channel = self._routes.get(route.route)

        if not channel:
            logger.error("Router %s returned invalid route %s", route)
            raise web.HTTPInternalServerError()

        if route.api is None:
            response = await ows_handler(
                request,
                channel=channel,
                project=route.project,
                cors_options_handler=cors_options_handler,
                collect=self._collect,
            )
        else:
            # Check if api endpoint is declared for the channel
            # Note: it is expected that the api path is relative to
            # the request path
            api = route.api
            for ep in channel.api_endpoints:
                if api == ep.endpoint:
                    logger.trace(
                        "Found endpoint '%s' (delegate to: %s) for path: %s",
                        ep.endpoint,
                        ep.delegate_to or "n/a",
                        route.path,
                    )
                    #
                    # Qgis server has a problem when resolving
                    # html template resource paths, so disable
                    # fetching html resources by default
                    #
                    if ep.delegate_to and not ep.enable_html_delegate:
                        if request.path.endswith('.html'):
                            raise web.HTTPUnsupportedMediaType()

                    api_name = ep.delegate_to or ep.endpoint
                    api_path = route.path or ""
                    response = await api_handler(
                        request,
                        channel=channel,
                        project=route.project,
                        api=api_name,
                        path=api_path,
                        delegate=bool(ep.delegate_to),
                        cors_options_handler=cors_options_handler,
                        collect=self._collect,
                    )
                    break
            else:
                raise web.HTTPNotFound()

        return response


#
# Server
#

Site: TypeAlias = web.TCPSite | web.UnixSite


@no_type_check
async def start_site(conf: HttpConfig, runner: web.AppRunner) -> Site:

    ssl_context = conf.ssl.create_ssl_server_context() if conf.use_ssl else None

    site: Site
    match conf.listen:
        case (address, port):
            site = web.TCPSite(
                runner,
                host=address.strip('[]'),
                port=port,
                ssl_context=ssl_context,
            )
        case socket:
            site = web.UnixSite(
                runner,
                socket[len('unix:'):],
                ssl_context=ssl_context,
            )

    await site.start()
    return site


@asynccontextmanager
async def setup_ogc_server(
    conf: ConfigProto,
    channels: Channels,
) -> AsyncGenerator[web.AppRunner, None]:

    app = web.Application(
        middlewares=[
            log_incoming_request,
            unhandled_exceptions,
        ],
        handler_args={
            'access_log_class': AccessLogger,
        },
    )

    # CORS support
    app.on_response_prepare.append(set_access_control_headers(conf.http.cross_origin))
    app.on_response_prepare.append(set_server_headers)

    router = _Router(channels, conf.router)

    metrics_service = None
    if conf.metrics:
        metrics_service = await router.set_metrics(conf.metrics)

        async def close_service(app: web.Application):
            await metrics_service.close()
        app.on_cleanup.append(close_service)

    async def favicon(request: web.Request) -> web.Response:
        return web.Response(status=204)

    async def forbidden(request: web.Request) -> web.Response:
        return web.Response(status=403)

    app.router.add_route('GET', '/favicon.ico', favicon)
    app.router.add_route('*', '/', forbidden)
    app.router.add_route('*', "/{tail:.+}", router.do_route)

    runner = web.AppRunner(app, handler_cancellation=True)
    await runner.setup()
    try:
        yield runner
    finally:
        await runner.cleanup()


@asynccontextmanager
async def setup_adm_server(
    conf: AdminHttpConfig,
    channels: Channels,
) -> AsyncGenerator[web.AppRunner, None]:
    """ Configure admin/managment server
    """
    logger.info(f"Configuring admin server at {conf.format_interface()}")

    app = web.Application(
        middlewares=[
            log_incoming_request,
            unhandled_exceptions,
        ],
        handler_args={
            'access_log_class': AccessLogger,
        },
    )

    # CORS support
    app.on_response_prepare.append(
        set_access_control_headers(conf.cross_origin),
    )

    async def favicon(request: web.Request) -> web.Response:
        return web.Response(status=204)

    app.add_routes(
        [
            web.get('/', admin_root),
            web.get('/favicon.ico', favicon),
            web.get('/backends', redirect('/backends/')),
            backends_route(channels, cors_options_handler),
            backends_list_route(channels, cors_options_handler),
            config_route(channels, cors_options_handler),
        ],
    )

    runner = web.AppRunner(app, handler_cancellation=True)
    await runner.setup()
    try:
        yield runner
    finally:
        await runner.cleanup()


async def serve(conf: ConfigProto):

    # Initialize channels
    channels = Channels(conf)
    await channels.init_channels()

    async with setup_ogc_server(conf, channels) as ogc_runner:
        async with setup_adm_server(conf.admin_http, channels) as adm_runner:

            _ogc_site: Site = await start_site(conf.http, ogc_runner)
            _adm_site: Site = await start_site(conf.admin_http, adm_runner)

            event = asyncio.Event()

            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGINT, event.set)
            loop.add_signal_handler(signal.SIGTERM, event.set)

            logger.info(f"Server listening at {conf.http.format_interface()}")
            await event.wait()

    await channels.close()
    logger.info("Server shutdown")
