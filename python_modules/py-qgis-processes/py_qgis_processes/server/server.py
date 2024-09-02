import asyncio
import signal
import traceback

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from textwrap import dedent as _D

from aiohttp import web
from aiohttp.abc import AbstractAccessLogger
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    Field,
)
from typing_extensions import (
    Awaitable,
    Callable,
    Literal,
    Optional,
    Protocol,
    TypeAlias,
    cast,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import (
    ConfigBase,
    NetInterface,
    SSLConfig,
    confservice,
    read_config_toml,
    section,
)

from . import swagger
from .accesspolicy import (
    AccessPolicyConfig,
    DummyAccessPolicy,
    create_access_policy,
)
from .cache import ProcessesCache
from .executor import Executor, ExecutorConfig
from .forwarded import ForwardedConfig, forwarded
from .handlers import API_VERSION, Handler
from .models import ErrorResponse, RequestHandler

try:
    __version__ = version('py_qgis_processes')
except PackageNotFoundError:
    __version__ = "dev"

SERVER_HEADER = f"Py-Qgis-Http-Processes {__version__}"


#
# Configuration
#

DEFAULT_INTERFACE = ("127.0.0.1", 9080)

HttpCORS: TypeAlias = Literal['all', 'same-origin'] | AnyHttpUrl


@section('server')
class ServerConfig(ConfigBase):

    listen: NetInterface = Field(
        default=DEFAULT_INTERFACE,
        title="Interfaces to listen to",
    )
    use_ssl: bool = Field(
        default=False,
        title="Use ssl",
    )
    ssl: SSLConfig = Field(
        default=SSLConfig(),
        title="SSL configuration",
    )
    cross_origin: HttpCORS = Field(
        default='all',
        title="CORS origin",
        description=_D(
            """
            Allows to specify origin for CORS. If set 'all' will set
            Access-Control-Allow-Origin to '*'; 'same-origin' return
            the same value as the 'Origin' request header.
            A url may may be specified, restricting allowed origin to
            this url.
            """,
        ),
    )
    proxy: ForwardedConfig = Field(default=ForwardedConfig())

    update_interval: int = Field(
        default=180,
        gt=0,
        title="Service update interval",
        description="Interval in seconds between update of avaialable services",
    )

    cache_grace_period: int = Field(
        default=5,
        title="Cache grace period",
        description=_D(
            """
            Number of update for which cached service data may survive
            loss of service availability.
            Thus, cached data will survive `cache_grace_period * update_interal`
            seconds in cache after the service is gone.
            """,
        ),
    )

    timeout: int = Field(20, gt=0, title="Backend request timeout")

    enable_ui: bool = Field(True, title="Enable Web UI")


def format_interface(conf: ServerConfig) -> str:
    match conf.listen:
        case (address, port):
            return f"{address}:{port}"
        case socket:
            return str(socket)


# Add ExecutorConfig section
confservice.add_section("executor", ExecutorConfig)


# Allow type validation
class ConfigProto(Protocol):
    logging: logger.LoggingConfig
    server: ServerConfig
    executor: ExecutorConfig
    access_policy: AccessPolicyConfig
    oapi: swagger.OapiConfig

    def model_dump_json(self, *args, **kwargs) -> str:
        ...


# Configuration loader helper
def load_configuration(
    configpath: Optional[Path],
) -> ConfigProto:

    if configpath:
        cnf = read_config_toml(
            configpath,
            location=str(configpath.parent.absolute()),
        )
    else:
        cnf = {}

    confservice.validate(cnf)
    return cast(ConfigProto, confservice.conf)


#
# Logging
#


REQ_FORMAT = (
    "{ip}\t{code}\t{method}\t{url}\t{time}\t{length}"
    "\t{agent}\t{referer}"
)
REQ_ID_FORMAT = "REQ-ID:{request_id}"


class AccessLogger(AbstractAccessLogger):
    """ Custom access logger
    """
    def log(self, request: web.BaseRequest, response: web.StreamResponse, duration: float):

        length = response.headers.get('Content-Length') or -1
        agent = request.headers.get('User-Agent', "")
        referer = request.headers.get('Referer', "")

        fmt = REQ_FORMAT.format(
            ip=request.remote,
            method=request.method,
            url=request.path,
            code=response.status,
            time=int(1000.0 * duration),
            length=length,
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
# Log incoming request with request id
#

RREQ_FORMAT = "{ip}\t{method}\t{url}\t{agent}\t{referer}\t" + REQ_FORMAT


@web.middleware
async def log_incoming_request(
    request: web.Request,
    handler: RequestHandler,
) -> web.StreamResponse:
    request_id = request.headers.get('X-Request-ID', "")
    if request_id:
        request['request_id'] = request_id
        agent = request.headers.get('User-Agent', "")
        referer = request.headers.get('Referer', "")

        fmt = RREQ_FORMAT.format(
            ip=request.remote,
            method=request.method,
            url=request.path,
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
async def unhandled_exceptions(
    request: web.Request,
    handler: RequestHandler,
) -> web.StreamResponse:
    try:
        return await handler(request)
    except web.HTTPException as e:
        if e.status == 404:
            ErrorResponse.raises(web.HTTPNotFound, e.reason)
        else:
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
# Server
#


Site: TypeAlias = web.TCPSite | web.UnixSite


def create_site(http: ServerConfig, runner: web.AppRunner) -> Site:

    ssl_context = http.ssl.create_ssl_server_context() if http.use_ssl else None

    site: Site

    match http.listen:
        case (str(address), int(port)):
            site = web.TCPSite(
                runner,
                host=address.strip('[]'),
                port=port,
                ssl_context=ssl_context,
            )
        case str(socket):
            site = web.UnixSite(
                runner,
                socket[len('unix:'):],
                ssl_context=ssl_context,
            )

    return site


def create_app(conf: ConfigProto) -> web.Application:

    app = web.Application(
        middlewares=[
            unhandled_exceptions,
            log_incoming_request,
            forwarded(conf.server.proxy),
        ],
        handler_args={
            'access_log_class': AccessLogger,
        },
    )

    # CORS support
    app.on_response_prepare.append(set_access_control_headers(conf.server.cross_origin))

    # Default server headers
    app.on_response_prepare.append(set_server_headers)

    # Executor
    executor = Executor(conf.executor)

    # Access policy
    access_policy = create_access_policy(conf.access_policy, app, executor)

    cache = ProcessesCache(conf.server.cache_grace_period)

    # Handler
    handler = Handler(
        executor=executor,
        policy=access_policy,
        timeout=conf.server.timeout,
        enable_ui=conf.server.enable_ui,
        cache=cache,
    )

    app.add_routes(handler.routes)

    # Create documentation model
    doc = _swagger_doc(app, conf.oapi)

    # Create router for the landing page
    async def landing_page(request: web.Request) -> web.Response:
        return web.Response(
            content_type="application/json",
            text=doc.model_dump_json(),
        )
    app.router.add_route('GET', '/', landing_page)

    # Add executor context
    app.cleanup_ctx.append(cache.cleanup_ctx(conf.server, executor))
    return app


def _swagger_doc(app: web.Application, oapi: swagger.OapiConfig) -> swagger.OpenApiDocument:
    return swagger.doc(
        app,
        api_version=API_VERSION,
        tags=[
            swagger.Tag(name="processes", description="Processes"),
            swagger.Tag(name="jobs", description="Jobs"),
            swagger.Tag(name="services", description="Services"),
        ],
        conf=oapi,
    )


def swagger_model(config: Optional[ConfigProto] = None) -> BaseModel:
    """ Return the swagger model
        for the REST api
    """
    handler = Handler(
        executor=cast(Executor, None),
        policy=DummyAccessPolicy(),
        cache=cast(ProcessesCache, None),
        timeout=0,
        enable_ui=False,
    )
    app = web.Application()
    app.add_routes(handler.routes)
    return _swagger_doc(app, config.oapi if config else swagger.OapiConfig())


async def _serve(conf: ConfigProto):
    """ Start the web server
    """
    app = create_app(conf)

    runner = web.AppRunner(app)

    await runner.setup()

    try:
        site = create_site(conf.server, runner)

        logger.info("Server listening at %s", format_interface(conf.server))
        await site.start()

        event = asyncio.Event()

        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, event.set)
        loop.add_signal_handler(signal.SIGTERM, event.set)

        await event.wait()
        logger.debug("Got signal")
    finally:
        logger.debug("Runner cleanup")
        await runner.cleanup()

    logger.info("Server shutdown")


def serve(conf: ConfigProto):
    asyncio.run(_serve(conf))
