from typing import (
    Awaitable,
    Callable,
    Literal,
    TypeAlias,
)

from aiohttp import web
from pydantic import AnyHttpUrl

HttpCORS: TypeAlias = Literal["all", "same-origin"] | AnyHttpUrl


#
# CORS
#

# Non-safelisted response headers that cross-origin
# clients are allowed to read
EXPOSE_HEADERS = (
    "Location, Content-Length, Last-Modified, X-Job-Id, X-Job-Realm, X-Request-ID, QJazz-Store-Type"
)


def cors_handler(
    allow_methods: str,
    allow_headers: str = "*",
) -> Callable[[web.Request], Awaitable[web.Response]]:
    """Set correct headers for 'OPTIONS' method"""

    async def cors_handler_(request: web.Request) -> web.Response:
        headers = {"Access-Control-Allow-Headers": allow_headers}
        if request.headers.get("Origin"):
            # Required in CORS context
            # see https://developer.mozilla.org/fr/docs/Web/HTTP/M%C3%A9thode/OPTIONS
            headers["Access-Control-Allow-Methods"] = allow_methods

        return web.Response(headers=headers)

    return cors_handler_


def set_access_control_headers(
    mode: HttpCORS,
) -> Callable[[web.Request, web.StreamResponse], Awaitable[None]]:
    """Build a response prepare callback"""

    async def set_access_control_headers_(
        request: web.Request,
        response: web.StreamResponse,
    ):
        """Handle Access control and cross origin headers (CORS)"""
        origin = request.headers.get("Origin")
        if origin:
            match mode:
                case "all":
                    allow_origin = "*"
                case "same-origin":
                    allow_origin = origin
                    response.headers["Vary"] = "Origin"
                case _ as url:
                    allow_origin = str(url)

            response.headers["Access-Control-Allow-Origin"] = allow_origin
            response.headers["Access-Control-Expose-Headers"] = EXPOSE_HEADERS

    return set_access_control_headers_  # typing: ignore [return-value]
