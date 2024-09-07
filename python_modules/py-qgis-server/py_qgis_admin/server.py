import asyncio
import traceback

from aiohttp import web
from aiohttp.abc import AbstractAccessLogger
from pydantic import (
    BaseModel,
)
from typing_extensions import (
    Any,
    Dict,
    Optional,
    cast,
    no_type_check,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import ConfigBase, ConfigProxy

from . import swagger
from .api import API_VERSION, ErrorResponse, Handlers
from .config import RESOLVERS_SECTION, ConfigProto, ResolverConfig, confservice
from .service import Service

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
            agent=agent,
        )

        logger.log_req(fmt)


def forwarded_for(request):
    """ Return the remote ip
    """
    return request.headers.get("X-Real-IP") or \
        request.headers.get("X-Forwarded-For") or \
        request.remote


def cors_options_headers(
    request: web.Request,
    headers: Dict[str, str],
    allow_headers: Optional[str] = None,
):
    """  Set correct headers for 'OPTIONS' method
    """
    allow_methods = "PUT, POST, GET, OPTIONS"
    headers["Allow"] = allow_methods
    headers['Access-Control-Allow-Headers'] = allow_headers or ALLOW_DEFAULT_HEADERS
    if request.headers.get('Origin'):
        # Required in CORS context
        # see https://developer.mozilla.org/fr/docs/Web/HTTP/M%C3%A9thode/OPTIONS
        headers['Access-Control-Allow-Methods'] = allow_methods


def set_access_control_headers(mode):
    """ Build a response prepare callback
    """
    async def set_access_control_headers_(request, response):
        """  Handle Access control and cross origin headers (CORS)
        """
        origin = request.headers.get('Origin')
        if not origin:
            return
        match mode:
            case 'all':
                allow_origin = '*'
            case 'same-origin':
                allow_origin = origin
                response.headers['Vary'] = 'Origin'
            case _ as url:
                allow_origin = str(url)

        response.headers['Access-Control-Allow-Origin'] = allow_origin

    return set_access_control_headers_


@web.middleware
async def authenticate(request, handler):
    """ Check token authentication
    """
    tokens = request.app['config'].auth_tokens
    if tokens is not None:
        # FIXME should not authorize if tokens are requested
        authorization = request.headers.get('Authorization')
        if authorization and authorization.startswith('Bearer '):
            token = authorization[7:]
            if token not in tokens:
                # Authentification failed
                raise web.HTTPUnauthorized(
                    headers={'WWW-Authenticate': 'Bearer realm="Qgis services admin api access'},
                    content_type="application/json",
                    text=ErrorResponse(message="Unauthorized").model_dump_json(),
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
            ).model_dump_json(),
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


def _swagger_doc(app):
    return swagger.doc(
        app,
        api_version=API_VERSION,
        tags=[
            swagger.Tag(name="pools", description="Manage pools"),
            swagger.Tag(name="pools.config", description="Manage pool's configuration"),
            swagger.Tag(name="pools.cache", description="Manage pool's cache"),
            swagger.Tag(name="pools.cache.project", description="Manage project in cache"),
            swagger.Tag(name="pools.plugins", description="Manage pool's plugins"),
        ],
    )


def swagger_model() -> BaseModel:
    """ Return the swagger model
        for the REST api
    """
    handlers = Handlers(cast(Service, None))
    app = web.Application()
    app.add_routes(handlers.routes)
    return _swagger_doc(app)


def create_app(conf: ConfigProto) -> web.Application:
    """ Create a web application
    """
    conf = cast(Any, conf)

    service = Service(
        cast(
            ResolverConfig,
            ConfigProxy(confservice, RESOLVERS_SECTION, default=conf.resolvers),
        ),
    )

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

    app.on_response_prepare.append(
        set_access_control_headers(conf.http.cross_origin),
    )

    # Routing
    app.add_routes(handlers.routes)

    # Create documentation model
    doc = _swagger_doc(app)

    # Create a router for the landing page
    async def landing_page(request):
        return web.Response(
            content_type="application/json",
            text=doc.model_dump_json(),
        )
    app.router.add_route('GET', '/', redirect(f'/{API_VERSION}'))
    app.router.add_route('GET', f'/{API_VERSION}', landing_page)
    return app


@no_type_check
def serve(conf: ConfigBase):
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
        ssl_context=conf.http.ssl.create_ssl_server_context() if conf.http.use_ssl else None,
        handle_signals=True,
        **listen,
    )
