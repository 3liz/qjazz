import asyncio
import signal
import traceback

from dataclasses import dataclass
from pathlib import PurePosixPath
from time import time

import tornado.httpserver
import tornado.httputil
import tornado.netutil
import tornado.routing
import tornado.web

from tornado.httputil import HTTPServerRequest
from tornado.web import HTTPError
from typing_extensions import Any, Callable, Iterator, List, Optional

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.condition import assert_precondition
from py_qgis_contrib.core.config import Config

from .channel import Channel
from .config import (
    AdminHttpConfig,
    BackendConfig,
    HttpConfig,
    HttpCORS,
    metrics,
)
from .handlers import (
    ApiHandler,
    BackendHandler,
    ConfigHandler,
    ErrorHandler,
    JsonNotFoundHandler,
    NotFoundHandler,
    OwsHandler,
    _BaseHandler,
)
from .router import DefaultRouter

#
# Router delegate
#

REQ_LOG_TEMPLATE = "{ip}\t{code}\t{method}\t{url}\t{time}\t{length}\t"
REQ_FORMAT = REQ_LOG_TEMPLATE + '{agent}\t{referer}'
REQ_ID_FORMAT = "REQ-ID:{request_id}"
RREQ_FORMAT = "{ip}\t{method}\t{url}\t{agent}\t{referer}\t" + REQ_ID_FORMAT


class App(tornado.web.Application):

    def __init__(self, *args, cross_origin: HttpCORS, **kwargs):
        super().__init__(*args, **kwargs)
        self._cross_origin = cross_origin

    @property
    def cross_origin(self) -> HttpCORS:
        return self._cross_origin

    def log_request(self, handler: _BaseHandler) -> None:   # type: ignore
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
            agent=agent,
        )

        if handler.request_id:
            fmt += f"\t{REQ_ID_FORMAT.format(request_id=handler.request_id)}"

        logger.log_req(fmt)

    def log_rrequest(self, request, request_id):
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
            request_id=request_id,
        )

        logger.log_rreq(fmt)


async def _init_channel(backend: BackendConfig) -> Channel:
    """  Initialize channel from backend
    """
    chan = Channel(backend)
    await chan.connect()
    return chan


class _Channels:
    """ Handle channels
    """

    def __init__(self, conf: Config):
        self._conf: Any = conf
        self._channels: List[Channel] = []
        self._last_modified = time()

    @property
    def conf(self) -> Config:
        return self._conf

    @property
    def backends(self) -> Iterator[Channel]:
        return iter(self._channels)

    @property
    def last_modified(self) -> float:
        return self._last_modified

    def is_modified_since(self, timestamp: float) -> bool:
        return self._last_modified > timestamp

    async def init_channels(self):
        # Initialize channels
        logger.info("Reconfiguring channels")
        channels = await asyncio.gather(*(_init_channel(be) for _, be in self._conf.backends.items()))
        # Close previous channels
        if self._channels:
            background_tasks = set()
            logger.trace("Closing current channels")
            # Run in background since we do want to wait for
            # grace period before
            task = asyncio.create_task(self.close(with_grace_period=True))
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)
        logger.trace("Setting new channels")
        self._channels = channels
        self._last_modified = time()

    async def close(self, with_grace_period: bool = False):
        channels = self._channels
        self._channels = []
        await asyncio.gather(*(chan.close(with_grace_period) for chan in channels))

    def get_backend(self, name: str) -> Optional[BackendConfig]:
        return self._conf.backends.get(name)

    async def add_backend(self, name: str, backend: BackendConfig):
        """ Add new backend (equivalent to POST)
        """
        assert_precondition(name not in self._conf.backends)
        self._conf.backends[name] = backend
        self._channels.append(await _init_channel(backend))

    def remove_backend(self, name: str) -> bool:
        """ Delete a specific backend from the list
        """
        backend = self._conf.backends.pop(name, None)
        if not backend:
            return False

        def _close():
            background_tasks = set()
            for chan in self._channels:
                if chan.address == backend.address:
                    task = asyncio.create_task(chan.close(with_grace_period=True))
                    background_tasks.add(task)
                    task.add_done_callback(background_tasks.discard)
                else:
                    yield chan
        self._channels = list(_close())
        return True


class _Router(tornado.routing.Router):
    """ Router
    """

    def __init__(self, channels: _Channels, conf: HttpConfig):
        self.channels = channels
        self.app = App(
            default_handler_class=NotFoundHandler,
            cross_origin=conf.cross_origin,
        )

        self._metrics_call: Optional[Callable] = None

        # Set router
        self._channels_last_modified = 0.
        self._router = DefaultRouter()
        self._update_routes()

    async def set_metrics(self, metrics_conf: metrics.MetricConfig) -> metrics.Metrics:
        """ Initialize metrics service
            if requested
        """
        _service = await metrics_conf.load_service()

        async def _call(request: HTTPServerRequest, chan: Channel, data: metrics.Data):
            routing_key = metrics_conf.routing_key_meta(
                meta=chan.meta,
                headers=request.headers,
            )
            if routing_key:
                await _service.emit(routing_key, data)

        self._metrics_call = _call
        return _service

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
            request: HTTPServerRequest

            def get_route(self) -> Optional[str]:  # type: ignore
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

    def _get_error_handler(
        self,
        request: HTTPServerRequest,
        code: int,
        reason: Optional[str] = None,
    ) -> tornado.httputil.HTTPMessageDelegate:
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
            # Update routes if required
            # XXX use event or barrier
            self._update_routes()

            route = self._router.route(
                self._routable_class(request=request),
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
                    {
                        'channel': channel,
                        'project': route.project,
                        'metrics': self._metrics_call,
                    },
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
                        # !IMPORTANT set the root url without the api path
                        request.path = request.path.removesuffix(api_path)
                        return self.app.get_handler_delegate(
                            request,
                            ApiHandler,
                            {
                                'channel': channel,
                                'project': route.project,
                                'api': api_name,
                                'path': api_path,
                                'delegate': bool(ep.delegate_to),
                                'metrics': self._metrics_call,
                            },
                        )

                return self._get_error_handler(request, 404)
        except HTTPError as err:
            return self._get_error_handler(request, err.status_code, err.reason)
        except Exception:
            logger.critical(traceback.format_exc())
            return self._get_error_handler(request, 500)


def configure_server(
    router: tornado.routing.Router,
    conf: HttpConfig,
) -> tornado.httpserver.HTTPServer:
    server = tornado.httpserver.HTTPServer(
        router,
        ssl_options=conf.ssl.create_ssl_server_context() if conf.use_ssl else None,
        xheaders=conf.proxy_conf,
    )
    match conf.listen:
        case (str(address), int(port)):
            server.listen(port, address=address.strip('[]'))
        case str(socket):
            socket = socket[len('unix:'):]
            socket = tornado.netutil.bind_unix_socket(socket)
            server.add_socket(socket)
    return server


def configure_admin_server(conf: AdminHttpConfig, channels: _Channels):
    """ Configure admin/managment server
    """
    logger.info(f"Configuring admin server at {conf.format_interface()}")
    configure_server(
        App(
            [
                (r"/backend/([^\/]+)$", BackendHandler, {'channels':  channels}),
                (r"/config", ConfigHandler, {'channels': channels}),
            ],
            default_handler_class=JsonNotFoundHandler,
            cross_origin=conf.cross_origin,
        ),
        conf,
    )


async def serve(conf: Config):

    # Config use dynamic attributs and
    # mypy cannot deal with that
    conf: Any = conf

    # Initialize channels
    channels = _Channels(conf)
    await channels.init_channels()

    router = _Router(channels, conf.http)

    metrics_service = None
    if conf.metrics:
        metrics_service = await router.set_metrics(conf.metrics)

    configure_server(router, conf.http)
    configure_admin_server(conf.admin_server, channels)

    event = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, event.set)
    loop.add_signal_handler(signal.SIGTERM, event.set)

    logger.info(f"Server listening at {conf.http.format_interface()}")
    await event.wait()
    await channels.close()

    if metrics_service:
        await metrics_service.close()

    logger.info("Server shutdown")
