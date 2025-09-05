from typing import Callable

from aiohttp import web
from qjazz_core.config import ConfigBase
from qjazz_core.models import Field

from .models import RequestHandler


class ForwardedConfig(ConfigBase):
    """Forwarded Configuration"""

    enable: bool = Field(
        default=False,
        title="Enabled Forwarded headers",
        description="""
        Enable proxy headers resolution.
        Include support for 'Forwarded' headers
        and 'X-Forwarded' headers if allow_x_headers is
        enabled."
        """,
    )
    allow_x_headers: bool = Field(
        default=False,
        title="Support for 'X-Forwarded' headers",
    )


def forwarded(conf: ForwardedConfig) -> Callable:
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
                host = request.headers.get("X-Forwarded-Host", host)
                proto = request.headers.get("X-Forwarded-Proto", proto)

            # Check for 'Forwarded'  headers as defined in RFC 7239
            # see https://docs.aiohttp.org/en/stable/web_reference.html#aiohttp.web.BaseRequest.forwarded
            forwarded = request.forwarded
            if forwarded:
                fwd = forwarded[0]  # The first proxy encountered by client
                host = fwd.get("host", host)
                proto = fwd.get("proto", proto)

        request["public_url"] = f"{proto}://{host}"

        return await handler(request)

    return middleware
