# import traceback
from typing import (  # noqa
    Dict,
    List,
    Literal,
    Optional,
    Self,
    Set,
    Type,
)

from aiohttp import web
from pydantic import (  # noqa
    BaseModel,
    Field,
    Json,
    TypeAdapter,
    ValidationError,
)

from qjazz_contrib.core import logger

from .. import service, swagger
from ..models import ErrorResponse

API_VERSION = "v1"


def _public_url(request: web.Request, path: str) -> str:
    """ Return the public base url
    """
    host = request.host
    protocol = request.scheme

    # Check for X-Forwarded-Host header
    forwarded_host = request.headers.get('X-Forwarded-Host')
    if forwarded_host:
        host = forwarded_host
    forwarded_proto = request.headers.get('X-Forwarded-Proto')
    if forwarded_proto:
        protocol = forwarded_proto

    # Check for 'Forwarded headers
    forwarded = request.headers.get('Forwarded')
    if forwarded:
        parts = forwarded.split(';')
        for p in parts:
            try:
                k, v = p.split('=')
                if k == 'host':
                    host = v.strip(' ')
                elif k == 'proto':
                    protocol = v.strip(' ')
            except Exception as e:
                logger.error("Forwaded header error: %s", e)
    return f"{protocol}://{host}{path}"


# ====================
# Services
# ====================

class BaseHandlers:
    def __init__(self, srvc: service.Service):
        self.service = srvc


def _href(request: web.Request, path: str) -> str:
    return _public_url(request, f"/{API_VERSION}{path}")


def _link(
    request: web.Request,
    rel: str,
    path: str,
    *,
    mime_type: str = "application/json",
    title: str = "",
    description: Optional[str] = None,
) -> swagger.Link:
    return swagger.Link(
        href=_href(request, path),
        rel=rel,
        mime_type=mime_type,
        title=title,
        description=description,
    )


def _http_error(
    error_type: Type[web.HTTPException],
    message: str,
    details: Optional[Json] = None,
):
    raise error_type(
        content_type="application/json",
        text=ErrorResponse(
            message=message,
            details=details,
        ).model_dump_json(),
    )


# Models utils
