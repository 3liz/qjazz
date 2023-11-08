import asyncio
import signal
import tornado.web
import tornado.httpserver
import tornado.netutil
import tornado.routing
import tornado.httputil
import traceback

from dataclasses import dataclass
from tornado.web import HTTPError

from pathlib import PurePosixPath

from typing_extensions import (
    Optional,
    List,
)

from py_qgis_contrib.core.config import Config
from py_qgis_contrib.core import logger

from .channel import Channel
from .router import DefaultRouter
from .config import SSLConfig
from .handlers import (
    _BaseHandler,
    NotFoundHandler,
    OwsHandler,
    ApiHandler,
    ErrorHandler,
)


#
# Router delegate
#

REQ_LOG_TEMPLATE = "{ip}\t{code}\t{method}\t{url}\t{time}\t{length}\t"
REQ_FORMAT = REQ_LOG_TEMPLATE + '{agent}\t{referer}'
REQ_ID_FORMAT = "REQ-ID:{request_id}"
RREQ_FORMAT = "{ip}\t{method}\t{url}\t{agent}\t{referer}\t" + REQ_ID_FORMAT


class App(tornado.web.Application):

    def log_request(self, handler: _BaseHandler) -> None:
        """ Format current request from the given tornado request handler
        """
        request = handler.request
        code = handler.get_status()
        reqtime = request.request_time()

        length = handler._headers.get('Content-Length') or -1
        agent = request.headers.get('User-Agent', "")
        referer = request.headers.get('Referer', "")

        fmt = REQ_FORMAT.format(
            ip=request.remote_ip,
            method=request.method,
            url=request.uri,
            code=code,
            time=int(1000.0 * reqtime),
            length=length,
            referer=referer,
            agent=agent
        )

        if handler.request_id:
            fmt += f"\t{REQ_ID_FORMAT.format(request_id=handler.request_id)}"

        logger.log_req(fmt)

    def log_rrequest(self, request, request_id) -> None:
        """ Log incoming request with request_id
        """
        agent = request.headers.get('User-Agent', "")
        referer = request.headers.get('Referer', "")

        fmt = RREQ_FORMAT.format(
            ip=request.remote_ip,
            method=request.method,
            url=request.uri,
            referer=referer,
            agent=agent,
            request_id=request_id
        )

        logger.log_rreq(fmt)


class _Router(tornado.routing.Router):
    """ Router
    """

    def __init__(self, proxy_conf, channels: List[Channel]):
        assert isinstance(channels, list), f"Expecting List, found {type(channels)}"
        self.channels = channels
        self.app = App(
            default_handler_class=NotFoundHandler,
            proxy_conf=proxy_conf,
        )

        # Set router
        self._router = DefaultRouter()
        self._update_routes()

    def _update_routes(self):
        """ Update routes and routable class
        """
        routes = {chan.route: chan for chan in self.channels}

        @dataclass
        class _Routable:
            request: tornado.httputil.HTTPServerRequest

            def get_route(self) -> Optional[str]:
                """
                Return a route (str) for the
                current request path.
                """
                path = PurePosixPath(self.request.path)
                for route in routes:
                    if path.is_relative_to(route):
                        return route

        self._routes = routes
        self._routable_class = _Routable

    def _get_error_handler(self, request, code: int, reason: Optional[str] = None):
        return self.app.get_handler_delegate(
            request,
            ErrorHandler,
            {"status_code": code, "reason": reason},
        )

    def find_handler(self, request, **kwargs):
        """ Override

            Ask inner router to return a `Route` object
        """
        try:
            route = self._router.route(
                self._routable_class(request=request)
            )
            logger.trace("Route %s found for %s", request.uri, route)
            channel = self._routes.get(route.route)

            if not channel:
                logger.error("Router %s returned invalid route %s", route)
                return self._get_error_handler(request, 500)

            if route.api is None:
                return self.app.get_handler_delegate(
                    request,
                    OwsHandler,
                    {'channel': channel, 'project': route.project},
                )
            else:
                # Check if api endpoint is declared for that the channel
                # Note: it is expected that the api path is relative to
                # the request path
                api = route.api
                for ep in channel.api_endpoints:
                    if api == ep.endpoint:
                        logger.trace("Found endpoint '%s' for path: %s", ep.endpoint, route.path)
                        api_name = ep.delegate_to or ep.endpoint
                        api_path = route.path or ""
                        # !IMPORTANT set the root url
                        request.path = request.path.removesuffix(api_path)
                        return self.app.get_handler_delegate(
                            request,
                            ApiHandler,
                            {
                                'channel': channel,
                                'project': route.project,
                                'api': api_name,
                                'path': api_path,
                            },
                        )
                return self._get_error_handler(request, 404)
        except HTTPError as err:
            return self._get_error_handler(request, err.status_code,  err.reason)
        except Exception:
            logger.critical(traceback.format_exc())
            return self._get_error_handler(request, 500)


def ssl_context(conf: SSLConfig):
    import ssl
    ssl_ctx = ssl.create_task_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_ctx.load_cert_chain(conf.cert, conf.key)
    return ssl_ctx


async def serve(conf: Config):

    async def _init_channel(backend):
        chan = Channel(backend)
        await chan.connect()
        return chan

    # Initialize channels
    channels = await asyncio.gather(*(_init_channel(be) for _, be in conf.backends.items()))

    router = _Router(conf.http.proxy_conf, channels)

    # TODO Dynamic channel configuration

    server = tornado.httpserver.HTTPServer(
        router,
        ssl_options=ssl_context(conf.http.ssl) if conf.http.use_ssl else None,
        xheaders=conf.http.proxy_conf,
    )

    match conf.http.listen:
        case (address, port):
            server.listen(port, address=address.strip('[]'))
        case socket:
            socket = socket[len('unix:'):]
            socket = tornado.netutil.bind_unix_socket(socket)
            server.add_socket(socket)

    event = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, event.set)
    loop.add_signal_handler(signal.SIGTERM, event.set)

    logger.info(f"Server listening at {conf.http.format_interface()}")
    await event.wait()

    await asyncio.gather(*(chan.close() for chan in channels))
    logger.info("Server shutdown")
