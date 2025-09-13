from typing import (
    List,
    Literal,
    Optional,
    Protocol,
    no_type_check,
)

from pydantic import AnyHttpUrl
from qjazz_core import logger
from qjazz_core.config import (
    ConfBuilder,
    ConfigBase,
    NetInterface,
    TLSConfig,
)
from qjazz_core.models import Field

from .resolvers import ResolverConfig

DEFAULT_INTERFACE = ("127.0.0.1", 9871)


class HttpConfig(ConfigBase):
    listen: NetInterface = Field(
        default=DEFAULT_INTERFACE,
        title="Interfaces to listen to",
    )

    use_ssl: bool = Field(
        default=False,
        title="Use ssl",
    )

    ssl: TLSConfig = Field(
        default=TLSConfig(),
        title="TLS certificats",
    )

    cross_origin: Literal["all", "same-origin"] | AnyHttpUrl = Field(
        default="all",
        title="CORS origin",
        description="""
        Allows to specify origin for CORS. If set 'all' will set
        Access-Control-Allow-Origin to '*'; 'same-origin' return
        the same value as the 'Origin' request header.
        An url may may be specified, restricting allowed origin to
        this url.
        """,
    )

    proxy_conf: bool = Field(
        default=False,
        title="Enable proxy_configuration",
        description="""
        Indicates that the server is behind a reverse proxy.
        This enable handling of forwarded proxy headers"
        """,
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


class ConfigUrl(ConfigBase):
    """Remote configuration settings"""

    ssl: TLSConfig = Field(
        default=TLSConfig(),
        title="TLS configuration",
    )
    url: Optional[AnyHttpUrl] = Field(
        default=None,
        title="External configuration Url",
        description="""
        The server will issue a GET method against this url at startup.
        The method should returns a valid configuration fragment.
        Note that this overrides all local settings.
        """,
    )

    async def load_configuration(self) -> bool:
        if not self.url:
            return False

        import aiohttp

        use_ssl = self.url.scheme == "https"

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


class ConfigProto(Protocol):
    logging: logger.LoggingConfig
    admin_config_url: ConfigUrl
    admin_http: HttpConfig
    resolvers: ResolverConfig


confservice = ConfBuilder()

confservice.add_section("admin_http", HttpConfig)
confservice.add_section("admin_config_url", ConfigUrl)
confservice.add_section("resolvers", ResolverConfig)


RESOLVERS_SECTION = "resolvers"
