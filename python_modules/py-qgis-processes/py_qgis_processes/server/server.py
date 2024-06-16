import asyncio
import signal
import traceback

from importlib.metadata import PackageNotFoundError, version

from aiohttp import web
from aiohttp.abc import AbstractAccessLogger
from pydantic import (
    AnyHttpUrl,
    Field,
)
from typing_extensions import (
    Awaitable,
    Callable,
    Literal,
    Optional,
    TypeAlias,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import (
    ConfigBase,
    NetInterface,
    SSLConfig,
    confservice,
    section,
)

from ..executor import Executor, ExecutorConfig
from .accesspolicy import AccessPolicyConfig, create_access_policy
from .forwarded import Forwarded, ForwardedConfig
from .handlers import Handler
from .models import ErrorResponse, RequestHandler

try:
    __version__ = version('py_qgis_processes')
except PackageNotFoundError:
    __version__ = "dev"

SERVER_HEADER = f"Py-Qgis-Http-Processes {__version__}"


#
# Configuration
#

DEFAULT_INTERFACE = ("127.0.0.1", 8340)

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
        description=(
            "Allows to specify origin for CORS. If set 'all' will set\n"
            "Access-Control-Allow-Origin to '*'; 'same-origin' return\n"
            "the same value as the 'Origin' request header.\n"
            "A url may may be specified, restricting allowed origin to\n"
            "this url."
        ),
    )
    proxy: ForwardedConfig = Field(default=ForwardedConfig())

    route_prefix: Optional[str] = Field(
        default=None,
        title="Route prefix",
        description=(
            "Prefix prepended to path.\n"
            "Can be use for customizing path for proxy or\n"
            "to add extra path parameters used in\n"
            "conjonction with acces policy."
        ),
    )

    timeout: int = Field(5, title="Backend request timeout")


def format_interface(conf: ServerConfig) -> str:
    match conf.listen:
        case (address, port):
            return f"{address}:{port}"
        case socket:
            return str(socket)


# Add ExecutorConfig section
confservice.add_section("executor", ExecutorConfig)


# Allow type validation
class ConfigProto:
    logging: logger.LoggingConfig
    server: ServerConfig
    executor: ExecutorConfig
    access_policy: AccessPolicyConfig

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
            Forwarded(conf.server.proxy),
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

    # Handler
    handler = Handler(
        executor=executor,
        policy=access_policy,
        timeout=conf.server.timeout,
        prefix=conf.server.route_prefix,
    )

    app.add_routes(handler.routes)

    async def executor_context(app: web.Application):
        # Set up update service task
        async def update_services():
            while True:
                try:
                    logger.info("Updating services")
                    await executor.update_services()
                    await asyncio.sleep(600)
                except Exception:
                    logger.error("Failed to update services: %s", traceback.format_exc())

        update_task = asyncio.create_task(update_services())

        yield
        logger.debug("Cancelling update task")
        update_task.cancel()

    app.cleanup_ctx.append(executor_context)
    return app


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
    finally:
        await runner.cleanup()

    logger.info("Server shutdown")


def serve(conf: ConfigProto):
    asyncio.run(_serve(conf))
