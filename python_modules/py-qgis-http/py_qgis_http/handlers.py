import tornado.web
import tornado.httpserver
import tornado.netutil
import tornado.routing
import tornado.httputil

from py_qgis_worker._grpc import (
    api_pb2,
)

from tornado.web import HTTPError
from typing_extensions import (
    Optional,
    Tuple,
    Sequence,
    Dict,
)

from urllib.parse import urlencode
from importlib.metadata import version, PackageNotFoundError

from py_qgis_contrib.core import logger

from .channel import Channel

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

    def get_metadata(self) -> Sequence[Tuple[str, str]]:
        return self._channel.get_metadata(
            (k.lower(), v) for k, v in self.request.headers.items()
        )


#
# OWS
#

class OwsHandler(_BaseHandler, RpcHandlerMixIn):
    """ OWS Handler
    """

    def initialize(self, channel: Channel, project: Optional[str] = None):
        super().initialize()
        self._project = project
        self._channel = channel

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

    async def _handle_request(self):
        arguments = {k.upper(): v[0] for k, v in self.request.arguments.items()}
        project = self._project
        service = _decode(arguments.pop('SERVICE', ""))
        request = _decode(arguments.pop('REQUEST', ""))
        version = _decode(arguments.pop('VERSION', ""))

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
                    options=urlencode(self.check_getfeature_limit(arguments)),
                    request_id=self.request_id,
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

    async def get(self):
        await self._handle_request()

    async def post(self):
        await self._handle_request()

    def options(self):
        self.set_option_headers()


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
        project: Optional[str] = None
    ):
        super().initialize()
        self._project = project
        self._channel = channel
        self._api = api
        self._path = path

    async def _handle_request(self, method: str):
        project = self._project

        # Get the base url as the base url
        url = self.get_url()
        req = self.request

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
                    options=urlencode(req.arguments),
                    request_id=self.request_id,
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
