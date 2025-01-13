from typing import (
    Awaitable,
    Optional,
    Protocol,
)

from aiohttp import web

from .models import Link


def public_url(request: web.Request, path: str) -> str:
    """ Return the public base url
    """
    host = request.host
    proto = request.scheme

    # Check for X-Forwarded-Host header
    forwarded_host = request.headers.get('X-Forwarded-Host')
    if forwarded_host:
        host = forwarded_host
    forwarded_proto = request.headers.get('X-Forwarded-Proto')
    if forwarded_proto:
        proto = forwarded_proto

    # Check for 'Forwarded'  headers as defined in RFC 7239
    # see https://docs.aiohttp.org/en/stable/web_reference.html#aiohttp.web.BaseRequest.forwarded
    forwarded = request.forwarded
    if forwarded:
        for k, v in forwarded[0].items():  # The first proxy encountered by client
            match k:
                case 'host':
                    host = v
                case 'proto':
                    proto = v

    return f"{proto}://{host}{path}"


def public_location(request: web.Request) -> str:
    return public_url(request, request.path)


class CORSHandler(Protocol):
    def __call__(
        self, request: web.Request,
        allow_methods: str,
        allow_headers: str,
    ) -> Awaitable[web.Response]:
        ...


def href(request: web.Request, path: str) -> str:
    return public_url(request, f"{path}")


def make_link(
    request: web.Request,
    *,
    rel: str,
    path: str,
    mime_type: str = "application/json",
    title: str = "",
    description: Optional[str] = None,
) -> Link:
    return Link(
        href=href(request, path),
        rel=rel,
        mime_type=mime_type,
        title=title,
        description=description,
    )


def _decode(key: str, b: str | bytes) -> str:
    match b:
        case bytes():
            return b.decode(errors='replace')
        case str():
            return b
        case _:
            raise web.HTTPBadRequest(f"Invalid argument for {key}")
