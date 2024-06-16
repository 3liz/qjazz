
from aiohttp import web
from pydantic import Field
from typing_extensions import Callable

from py_qgis_contrib.core.config import ConfigBase

from .models import RequestHandler


class ForwardedConfig(ConfigBase):
    """Forwarded Configuration"""
    enable: bool = Field(
        default=False,
        title="Enabled Forwarded headers",
        description=(
            "Enable proxy headers resolution.\n"
            "Include support for 'Forwarded' headers\n"
            "and 'X-Forwarded' headers if allow_x_headers is \n"
            "enabled."
        ),
    )
    allow_x_headers: bool = Field(
        default=False,
        title="Support for 'X-Forwarded' headers",
    )


def Forwarded(conf: ForwardedConfig) -> Callable:

    @web.middleware
    async def middleware(
        request: web.Request,
        handler: RequestHandler,
    ) -> web.StreamResponse:

        host = request.host
        proto = request.scheme

        if conf.enable:
            if conf.allow_x_headers:
                # Check for X-Forwarded-Host header
                host = request.headers.get('X-Forwarded-Host', host)
                proto = request.headers.get('X-Forwarded-Proto', proto)

            # Check for 'Forwarded'  headers as defined in RFC 7239
            # see https://docs.aiohttp.org/en/stable/web_reference.html#aiohttp.web.BaseRequest.forwarded
            forwarded = request.forwarded
            if forwarded:
                fwd = forwarded[0]  # The first proxy encountered by client
                host = fwd.get('host', host)
                proto = fwd.get('proto', proto)

        request['public_url'] = f"{proto}://{host}"

        return await handler(request)

    return middleware
