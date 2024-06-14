from aiohttp import web
from typing_extensions import (
    Optional,
)

from ..processing.schemas import LinkHttp

Link = LinkHttp


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


# XXX take code from
# https://github.com/aio-libs/aiohttp-remotes/blob/master/aiohttp_remotes/forwarded.py
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


def href(request: web.Request, path: str) -> str:
    return public_url(request, f"{path}")


def redirect(path):
    """ Helper for creating redirect handler
    """
    async def _redirect(request):  # noqa RUF029
        raise web.HTTPFound(path)

    return _redirect
