import json
import os

from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import time
from urllib.parse import urlencode

import tornado.httpserver
import tornado.httputil
import tornado.netutil
import tornado.routing
import tornado.web

from pydantic import ValidationError
from tornado.web import HTTPError
from typing_extensions import Any, Callable, Dict, Optional, Sequence, Tuple

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.utils import to_rfc822
from py_qgis_worker._grpc import api_pb2

from . import metrics
from .channel import Channel
from .config import (
    ENV_CONFIGFILE,
    BackendConfig,
    RemoteConfigError,
    confservice,
    load_include_config_files,
    read_config_toml,
)

try:
    __version__ = version('py_qgis_http')
except PackageNotFoundError:
    __version__ = "dev"

ALLOW_DEFAULT_HEADERS = (
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


def _decode(b: str | bytes) -> str:
    if b and isinstance(b, bytes):
        return b.decode('utf-8')
    return b


class _BaseHandler(tornado.web.RequestHandler):

    def initialize(self):
        self.connection_closed = False
        self.request_id = ""

    def prepare(self):
        self.request_id = self.request.headers.get('X-Request-ID', "")
        if self.request_id:
            self.application.log_rrequest(self.request, self.request_id)
        if self.request.method != "OPTIONS":
            self.set_access_control_headers()

    def on_connection_close(self) -> None:
        """ Override, log and set 'connection_closed' to True
        """
        self.connection_closed = True
        logger.warning(f"Connection closed by client: {self.request.host}")

    def compute_etag(self) -> None:
        # Disable etag computation
        pass

    def set_default_headers(self) -> None:
        """ Override defaults HTTP headers
        """
        # XXX By default tornado set Content-Type to xml/text
        # this may have unwanted side effects
        self.clear_header("Content-Type")
        self.set_header("Server", f"Py-Qgis-Http-Server {__version__}")

    def set_option_headers(
        self,
        allow_methods: Optional[str] = None,
        allow_headers: Optional[str] = None
    ) -> None:
        """  Set correct headers for 'OPTIONS' method
        """
        self.set_header("Allow", allow_methods or "POST, GET, OPTIONS")
        self.set_header('Access-Control-Allow-Headers', allow_headers or ALLOW_DEFAULT_HEADERS)
        if self.set_access_control_headers():
            # Required in CORS context
            # see https://developer.mozilla.org/fr/docs/Web/HTTP/M%C3%A9thode/OPTIONS
            self.set_header('Access-Control-Allow-Methods', allow_methods)

    def set_access_control_headers(self) -> bool:
        """  Handle Access control and cross origin headers (CORS)
        """
        origin = self.request.headers.get('Origin')
        if origin:
            if self._cross_origin:
                self.set_header('Access-Control-Allow-Origin', '*')
            else:
                self.set_header('Access-Control-Allow-Origin', origin)
                self.set_header('Vary', 'Origin')
            return True
        else:
            return False

    def resolve_base_url(self) -> None:
        """ Resolve base url: protocol and host
        """
        req = self.request
        # Check for X-Forwarded-Host header
        forwarded_host = req.headers.get('X-Forwarded-Host')
        if forwarded_host:
            req.host = forwarded_host

        # Check for 'Forwarded headers
        forwarded = req.headers.get('Forwarded')
        if forwarded:
            parts = forwarded.split(';')
            for p in parts:
                try:
                    k, v = p.split('=')
                    if k == 'host':
                        req.host = v.strip(' ')
                    elif k == 'proto':
                        req.protocol = v.strip(' ')
                except Exception as e:
                    logger.error("Forwaded header error: %s", e)

    def get_url(self) -> str:
        """ Get proxy url
        """
        self.resolve_base_url()
        # Return the full uri without query
        req = self.request
        return f"{req.protocol}://{req.host}{req.path}"

    def options(self):
        self.set_option_headers()


#
# Error Handlers
#

class NotFoundHandler(_BaseHandler):
    def prepare(self):  # for all methods
        super().prepare()
        raise HTTPError(
            status_code=404,
            reason="Invalid resource path."
        )


class ErrorHandler(_BaseHandler):
    def initialize(self, status_code: int, reason: Optional[str] = None) -> None:
        super().initialize()
        self.set_status(status_code)
        self.reason = reason

    def prepare(self) -> None:
        super().prepare()
        raise HTTPError(self._status_code, reason=self.reason)


#
# Qgis request Handlers
#

# debug report
async def get_report(stream) -> Tuple[Optional[int], Optional[int]]:
    """ Return debug report from trailing_metadata
    """
    md = await stream.trailing_metadata()
    memory, duration, timestamp = None, None, None
    for k, v in md:
        match k:
            case 'x-debug-memory':
                memory = int(v)
            case 'x-debug-duration':
                duration = int(float(v) * 1000.0)
    return (memory, duration, timestamp)


class RpcHandlerMixIn:

    def write_response_headers(self, metadata) -> None:
        """ write response headers and return
            status code
        """
        status_code = 200
        for k, v in metadata:
            match k:
                case "x-reply-status-code":
                    status_code = int(v)
                case n if n.startswith("x-reply-header-"):
                    self.set_header(n.replace("x-reply-header-", "", 1), v)
        self.set_status(status_code)

    def get_metadata(self) -> Sequence[Tuple[str, str]]:
        return self._channel.get_metadata(
            (k.lower(), v) for k, v in self.request.headers.items()
        )

    @asynccontextmanager
    async def collect_metrics(self, service: str, request: str) -> bool:
        """ Emit metrics
        """
        if self._metrics:
            start = time()
            try:
                yield True
                status_code = self.get_status()
            except HTTPError as err:
                status_code = err.status_code
            finally:
                if not self._report:
                    logger.error("Something prevented to get metric's report...")
                    return
                project = self._project
                latency = int((time() - start) * 1000.)
                memory, duration, _ = self._report
                latency -= duration
                await self._metrics(
                    self.request,
                    self._channel,
                    metrics.Data(
                        status=status_code,
                        service=service,
                        request=request,
                        project=project,
                        memory_footprint=memory,
                        response_time=duration,
                        latency=latency,
                        cached=self._headers.get('X-Qgis-Cache') == 'HIT',
                    )
                )
        else:
            yield False

#
# OWS
#


class OwsHandler(_BaseHandler, RpcHandlerMixIn):
    """ OWS Handler
    """

    def initialize(
        self,
        channel: Channel,
        project: Optional[str] = None,
        metrics: Optional[Callable[[metrics.Data], None]] = None,
    ):
        super().initialize()
        self._project = project
        self._channel = channel
        self._metrics = metrics
        self._report = None

    def check_getfeature_limit(self, arguments: Dict) -> Dict:
        """ Take care of WFS/GetFeature limit

            Qgis does not set a default limit and unlimited
            request may cause issues
        """
        limit = self._channel.getfeature_limit
        if limit \
                and arguments.get('SERVICE', b'').upper() == b'WFS' \
                and arguments.get('REQUEST', b'').lower() == b'getfeature':

            if arguments.get('VERSION', b'').startswith(b'2.'):
                key = 'COUNT'
            else:
                key = 'MAXFEATURES'

            try:
                actual_limit = int(arguments.get(key, 0))
                if actual_limit > 0:
                    limit = min(limit, actual_limit)
            except ValueError:
                pass
            arguments[key] = str(limit).encode()

        return arguments

    async def _execute_request(
        self,
        arguments,
        service: str,
        request: str,
        version: str,
        report: bool = False,
    ):
        project = self._project

        url = self.get_url()
        metadata = self.get_metadata()

        async with self._channel.stub() as stub:
            stream = stub.ExecuteOwsRequest(
                api_pb2.OwsRequest(
                    service=service,
                    request=request,
                    version=version,
                    target=project,
                    url=url,
                    direct=self._channel.allow_direct_resolution,
                    options=urlencode(self.check_getfeature_limit(arguments), doseq=True),
                    request_id=self.request_id,
                    debug_report=report,
                ),
                metadata=metadata,
                timeout=self._channel.timeout,
            )

            self.write_response_headers(await stream.initial_metadata())

            async for chunk in stream:
                if self.connection_closed:
                    stream.cancel()
                    break
                self.write(chunk.chunk)
                await self.flush()

            if report:
                self._report = await get_report(stream)

    async def _handle_request(self):
        arguments = {k.upper(): v[0] for k, v in self.request.arguments.items()}
        service = _decode(arguments.pop('SERVICE', ""))
        request = _decode(arguments.pop('REQUEST', ""))
        version = _decode(arguments.pop('VERSION', ""))

        async with self.collect_metrics(service, request) as report:
            await self._execute_request(arguments, service, request, version, report=report)

    async def get(self):
        await self._handle_request()

    async def post(self):
        await self._handle_request()


#
# API
#

class ApiHandler(_BaseHandler, RpcHandlerMixIn):
    """ Api Handler
    """

    def initialize(
        self,
        channel: Channel,
        api: str,
        path: str = "/",
        project: Optional[str] = None,
        metrics: Optional[Callable[[metrics.Data], None]] = None,
    ):
        super().initialize()
        self._project = project
        self._channel = channel
        self._api = api
        self._path = path
        self._metrics = metrics
        self._report = None

    async def _execute_request(self, method: str, report: bool = False):
        project = self._project

        # Get the url as the base url
        url = self.get_url()
        req = self.request

        arguments = req.arguments
        metadata = self.get_metadata()

        async with self._channel.stub() as stub:
            stream = stub.ExecuteApiRequest(
                api_pb2.ApiRequest(
                    name=self._api,
                    path=self._path,
                    method=method,
                    data=req.body,
                    target=project,
                    url=url,
                    direct=self._channel.allow_direct_resolution,
                    # XXX Check for request query
                    options=urlencode(arguments, doseq=True),
                    request_id=self.request_id,
                    debug_report=report,
                ),
                metadata=metadata,
                timeout=self._channel.timeout,
            )

            self.write_response_headers(await stream.initial_metadata())

            if method == 'HEAD':
                stream.cancel()
                return

            async for chunk in stream:
                if self.connection_closed:
                    stream.cancel()
                    break
                self.write(chunk.chunk)
                await self.flush()

            if report:
                self._report = await get_report(stream)

    async def _handle_request(self, method: str):
        async with self.collect_metrics(self._api, self._path) as report:
            await self._execute_request(method, report=report)

    async def get(self):
        await self._handle_request("GET")

    async def post(self):
        await self._handle_request("POST")

    async def put(self):
        await self._handle_request("PUT")

    async def head(self):
        await self._handle_request("HEAD")

    async def patch(self):
        await self._handle_request("PATCH")


#
# Backend managment handler
#

class JsonErrorMixin:
    """ Override write error to return json errors
    """

    def write_error(self, status_code: int, **kwargs: Any) -> None:
        """ Override, format error as json
        """
        self.set_header("Content-Type", "application/json")
        self.finish(
            {
                "code": status_code,
                "message": self._reason,
            }
        )

    def write_json(self, chunk: Optional[str | bytes | dict]):
        self.set_header("Content-Type", "application/json")
        self.write(chunk)


class JsonNotFoundHandler(JsonErrorMixin, NotFoundHandler):
    pass


class BackendHandler(JsonErrorMixin, _BaseHandler):
    """ Admin Handler
    """

    def initialize(self, channels):
        super().initialize()
        self._channels = channels

    def get(self, name: str):
        """ Get backend
        """
        backend = self._channels.get_backend(name)
        if not backend:
            raise HTTPError(404, reason=f"Backend '{name}' does not exists")
        self.write_json(backend.model_dump_json())

    async def post(self, name: str):
        """ Add new backend
        """
        if self._channels.get_backend(name):
            raise HTTPError(409, reason=f"Backend '{name}' already exists")
        try:
            backend = BackendConfig.model_validate_json(self.request.body)
            await self._channels.add_backend(name, backend)
            self.set_header("Location", self.get_url())
            self.set_status(201)
        except ValidationError as err:
            raise HTTPError(400, reason=str(err))

    async def put(self, name):
        """ Replace backend
        """
        if not self._channels.get_backend(name):
            raise HTTPError(404, f"Backend '{name}' does not exists")
        try:
            backend = BackendConfig.model_validate_json(self.request.body)
            self._channels.remove_backend(name)
            await self._channels.add_backend(name, backend)
        except ValidationError as err:
            raise HTTPError(400, reason=str(err))

    def head(self, name):
        if not self._channels.get_backend(name):
            raise HTTPError(404, "Backend {name} does not exists")
        self.set_header("Content-Type", "application/json")

#
# Config managment handler
#


class ConfigHandler(JsonErrorMixin, _BaseHandler):
    """ Configuration Handler
    """

    def initialize(self, channels):
        super().initialize()
        self._channels = channels

    def get(self):
        """ Return actual configuration
        """
        self.set_header("Last-Modified", to_rfc822(confservice.last_modified))
        self.write_json(confservice.conf.model_dump_json())

    async def patch(self):
        """ Patch configuration with request content
        """
        try:
            obj = json.loads(self.request.body)
            confservice.update_config(obj)

            level = logger.set_log_level()
            logger.info("Log level set to %s", level.name)

            # Resync channels
            await self._channels.init_channels()
        except (json.JSONDecodeError, ValidationError) as err:
            raise HTTPError(400, reason=str(err))

    async def put(self):
        """ Reload configuration
        """
        # If remote url is defined, load configuration
        # from it
        config_url = confservice.conf.config_url
        try:
            if config_url.is_set():
                await config_url.load_configuration()
            elif ENV_CONFIGFILE in os.environ:
                # Fallback to configfile (if any)
                configpath = os.environ[ENV_CONFIGFILE]
                configpath = Path(configpath)
                logger.info("** Reloading config from %s **", configpath)
                obj = read_config_toml(
                    configpath,
                    location=str(configpath.parent.absolute()),
                )
            else:
                obj = {}

            confservice.update_config(obj)
            if confservice.conf.includes:
                load_include_config_files(confservice.conf)
            # Update log level
            level = logger.set_log_level()
            logger.info("Log level set to %s", level.name)

            # Resync channels
            await self._channels.init_channels()
        except RemoteConfigError as err:
            raise HTTPError(502, reason=str(err))
        except ValidationError as err:
            raise HTTPError(400, reason=str(err))
