from aiohttp import web
from typing_extensions import Optional

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


def public_url(request: web.Request, path: str) -> str:
    """ Return the public base url
    """
    return f"{request['public_url']}{path}"


def href(request: web.Request, path: str) -> str:
    return public_url(request, f"{path}")


def redirect(path):
    """ Helper for creating redirect handler
    """
    async def _redirect(request):  # noqa RUF029
        raise web.HTTPFound(path)

    return _redirect


def redirect_trailing_slash():
    """ Redirect with a trailing slash
    """
    async def _redirect(request):  # noqa RUF029
        qs = request.query_string
        path = f"{request.path}/?{qs}" if qs else f"{request.path}/"
        raise web.HTTPFound(path)

    return _redirect
