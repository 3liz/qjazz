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
    Mapping,
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


class ProxyConfig(ConfigBase):
    """Proxy Configuration"""
    resolve_proxy_headers: bool = Field(
        default=False,
        title="Proxy headers",
        description=(
            "Enable proxy headers resolution.\n"
            "Include support for 'Forwarded' headers\n"
            "and 'X-Forwarded' hedaers if x_headers is \n"
            "enabled."
        ),
    )
    x_headers: bool = Field(
        default=False,
        title="Support for 'X-Forwarded' headers",
    )
    prefix_path: Optional[str] = Field(
        default="",
        title="Prefix path",
    )


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
    proxy: ProxyConfig = Field(default=ProxyConfig())

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
RREQ_FORMAT = "{ip}\t{method}\t{url}\t{agent}\t{referer}\t" + REQ_FORMAT


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


def create_app(conf: ConfigProto) -> web.Application:

    middlewares = [
        log_incoming_request,
        unhandled_exceptions,
    ]

    # Executor
    executor = Executor(conf.executor)

    # Access policy
    access_policy = create_access_policy(conf.access_policy, executor)
    policy_middleware = access_policy.middleware()
    if policy_middleware:
        middlewares.append(policy_middleware)

    app = web.Application(
        middlewares=middlewares,
        handler_args={
            'access_log_class': AccessLogger,
        },
    )

    # CORS support
    app.on_response_prepare.append(set_access_control_headers(conf.server.cross_origin))

    # Default server headers
    app.on_response_prepare.append(set_server_headers)

    # Handler
    handler = Handler(
        executor=executor,
        policy=access_policy,
        timeout=conf.server.timeout,
    )

    app.add_routes(handler.routes)

    # See https://docs.aiohttp.org/en/stable/web_advanced.html#cleanup-context
    # TODO app.cleanup_ctx(executor_context(executor))

    return app


def serve(conf: ConfigProto):
    """ Start the web server
    """
    app = create_app(conf)

    http = conf.server

    listen: Mapping
    match http.listen:
        case (str(address), int(port)):
            listen = dict(host=address.strip('[]'), port=port)
        case str(socket):
            listen = dict(path=socket[len('unix:'):])

    logger.info("Server listening at %s", format_interface(conf.server))
    web.run_app(
        app,
        ssl_context=http.ssl.create_ssl_server_context() if http.use_ssl else None,
        handle_signals=True,
        **listen,
    )
