from pydantic import AnyHttpUrl, Field
from typing_extensions import List, Literal, Optional, no_type_check

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import (
    Config,
    NetInterface,
    SSLConfig,
    confservice,
    section,
)

DEFAULT_INTERFACE = ("127.0.0.1", 9871)


@section('http')
class HttpConfig(Config):

    listen: NetInterface = Field(
        default=DEFAULT_INTERFACE,
        title="Interfaces to listen to",
    )

    use_ssl: bool = Field(
        default=False,
        title="Use ssl",
    )

    ssl: SSLConfig = Field(
        default=SSLConfig(),
        title="SSL certificats",
    )

    cross_origin: Literal['all', 'same-origin'] | AnyHttpUrl = Field(
        default='all',
        title="CORS origin",
        description=(
            "Allows to specify origin for CORS. If set 'all' will set\n"
            "Access-Control-Allow-Origin to '*'; 'same-origin' return\n"
            "the same value as the 'Origin' request header.\n"
            "An url may may be specified, restricting allowed origin to "
            "this url."
        ),
    )

    proxy_conf: bool = Field(
        default=False,
        title="Enable proxy_configuration",
        description=(
            "Indicates that the server is behind a reverse proxy.\n"
            "This enable handling of forwarded proxy headers"
        ),
    )

    auth_tokens: List[str] = Field(
        default=[],
        description="List of authorized tokens",
    )

    @no_type_check
    def format_interface(self) -> str:
        match self.listen:
            case (address, port):
                return f"{address}:{port}"
            case socket:
                return socket


EXTERNAL_CONFIG_SECTION = "config_url"


@section(EXTERNAL_CONFIG_SECTION)
class ConfigUrl(Config):
    """Remote configuration settings"""
    ssl: SSLConfig = Field(
        default=SSLConfig(),
        title="SSL configuration",
    )
    url: Optional[AnyHttpUrl] = Field(
        default=None,
        title="External configuration Url",
        description=(
            "The server will issue a GET method against this url at startup.\n"
            "The method should returns a valid configuration fragment.\n"
            "Note that this overrides all local settings."
        ),
    )

    async def load_configuration(self) -> bool:
        if not self.url:
            return False

        import aiohttp

        use_ssl = self.url.scheme == 'https'

        async with aiohttp.ClientSession() as session:
            logger.info("Loading configuration from %s", self.url)
            async with session.get(
                str(self.url),
                ssl=self.ssl.create_ssl_client_context() if use_ssl else False,
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(
                        f"Failed to load configuration from {self.url}: error {resp.status}",
                    )
                cnf = await resp.json()
                logger.debug("Updating configuration:\n%s", cnf)
                confservice.update_config(cnf)

        return True
