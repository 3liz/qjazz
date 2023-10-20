import asyncio
import traceback
from aiohttp import web
from aiohttp.abc import AbstractAccessLogger


from pydantic import (  # noqa
    BaseModel,
    Field,
    Json,
    TypeAdapter,
    ValidationError,
)

from typing_extensions import (  # noqa
    Literal,
    Optional,
    List,
    Set,
    Dict,
    Self,
    Type,
)


from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import (
    Config,
    ConfigProxy,
    SSLConfig,
)

from . import swagger

from .service import Service
from .api import (
    Handlers,
    ErrorResponse,
    API_VERSION,
)

from .resolvers import RESOLVERS_SECTION

from . import config as server_config   # noqa


# routes = web.RouteTableDef()

# Required if the request has an "Authorization" header.
# This is useful to implement authentification on top QGIS SERVER
# see https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Access-Control-Allow-Headers &
# https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Authorization
ALLOW_DEFAULT_HEADERS = "Authorization"


REQ_LOG_TEMPLATE = "{ip}\t{code}\t{method}\t{url}\t{time}\t{length}\t"
REQ_FORMAT = REQ_LOG_TEMPLATE + '{agent}\t{referer}'


class AccessLogger(AbstractAccessLogger):
    """ Custom access logger
    """

    def log(self, request, response, time):

        length = response.headers.get('Content-Length') or -1
        agent = request.headers.get('User-Agent', "")
        referer = request.headers.get('Referer', "")

        fmt = REQ_FORMAT.format(
            ip=request.remote,
            method=request.method,
            url=request.path,
            code=response.status,
            time=int(1000.0 * time),
            length=length,
            referer=referer,
            agent=agent
        )

        logger.log_req(fmt)


def forwarded_for(request):
    """ Return the remote ip
    """
    return request.headers.get("X-Real-IP") or \
        request.headers.get("X-Forwarded-For") or \
        request.remote


def cors_options_headers(
    request,
    headers,
    allow_methods: str,
    allow_headers: Optional[str] = None
) -> Dict[str, str]:
    """  Set correct headers for 'OPTIONS' method
    """
    allow_methods = "PUT, POST, GET, OPTIONS"
    headers["Allow"] = allow_methods
    headers['Access-Control-Allow-Headers'] = allow_headers or ALLOW_DEFAULT_HEADERS
    if request.origin.get('Origin'):
        # Required in CORS context
        # see https://developer.mozilla.org/fr/docs/Web/HTTP/M%C3%A9thode/OPTIONS
        headers['Access-Control-Allow-Methods'] = allow_methods


async def set_access_control_headers(request, response):
    """  Handle Access control and cross origin headers (CORS)
    """
    origin = request.headers.get('Origin')
    if origin:
        response.headers['Access-Control-Allow-Origin'] = '*'


@web.middleware
async def authenticate(request, handler):
    """ Check token authentication
    """
    tokens = request.app['config'].auth_tokens
    if tokens is not None:
        authorization = request.headers.get('Authorization')
        if authorization and authorization.startswith('Bearer '):
            token = authorization[7:]
            if token not in tokens:
                # Authentification failed
                raise web.HTTPUnauthorized(
                    headers={'WWW-Authenticate': 'Bearer realm="Qgis services admin api access'},
                    content_type="application/json",
                    text=ErrorResponse(message="Unauthorized").model_dump_json()
                )
    return await handler(request)


@web.middleware
async def unhandled_exceptions(request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception:
        logger.critical(f"Error handling request:\n{traceback.format_exc()}")
        raise web.HTTPInternalServerError(
            content_type="application/json",
            text=ErrorResponse(
                message="Internal server error",
            ).model_dump_json()
        ) from None


#
#  Run server
#

def redirect(path):
    """ Helper for creating redirect handler
    """
    async def _redirect(request):
        raise web.HTTPFound(path)

    return _redirect


def ssl_context(conf: SSLConfig):
    import ssl
    ssl_ctx = ssl.create_task_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_ctx.load_cert_chain(conf.cert, conf.key)
    return ssl_ctx


def create_app(conf: Config):
    """ Create a web application
    """
    service = Service(ConfigProxy(RESOLVERS_SECTION, _default=conf.resolvers))

    asyncio.run(service.synchronize())

    handlers = Handlers(service)

    app = web.Application(
        middlewares=[
            unhandled_exceptions,
            authenticate,
        ],
        handler_args={
            'access_log_class': AccessLogger,
        },
    )

    app.on_response_prepare.append(set_access_control_headers)

    # Routing
    app.add_routes(handlers.routes)

    doc = swagger.doc(
        app,
        api_version=API_VERSION,
        tags=[
            swagger.Tag(name="backends", description="Manage backends"),
            swagger.Tag(name="backends.config", description="Manage backend's configuration"),
            swagger.Tag(name="backends.cache", description="Manage backend's cache"),
            swagger.Tag(name="backends.cache.project", description="Manage project in cache"),
            swagger.Tag(name="backends.plugins", description="Manage backend's plugins"),
        ]
    )

    app['swagger_doc'] = doc

    # Create a router for the landing page
    async def landing_page(request):
        return web.Response(
            content_type="application/json",
            text=doc.model_dump_json(),
        )
    app.router.add_route('GET', '/', redirect(f'/{API_VERSION}'))
    app.router.add_route('GET', f'/{API_VERSION}', landing_page)
    return app


def serve(conf: Config):
    """ Start the web server
    """
    app = create_app(conf)
    app['config'] = conf.http

    match conf.http.listen:
        case (address, port):
            listen = dict(host=address.strip('[]'), port=port)
        case socket:
            listen = dict(path=socket[len('unix:'):])

    logger.info(f"Server listening at {conf.http.format_interface()}")
    web.run_app(
        app,
        ssl_context=ssl_context(conf.http.ssl) if conf.http.use_ssl else None,
        handle_signals=True,
        **listen,
    )
