from pydantic import (
    AfterValidator,
    Field,
    AnyHttpUrl,
)

from typing_extensions import (
    Annotated,
    Literal,
    List,
    Optional,
)

from py_qgis_contrib.core.config import (
    Config,
    SSLConfig,
    NetInterface,
    section,
    confservice,
)

from py_qgis_contrib.core import logger


DEFAULT_INTERFACE = ("0.0.0.0", 9871)


def _check_ssl_config(sslconf):
    match (sslconf.key, sslconf.cert):
        case (str(), None):
            raise ValueError("Missing ssl cert file")
        case (None, str()):
            raise ValueError("Missing ssl key file")
    return sslconf


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

    ssl: Annotated[
        SSLConfig,
        AfterValidator(_check_ssl_config)
    ] = Field(
        default=SSLConfig(),
        title="SSL configuration",
    )

    cross_origin: Literal['all', 'same-origin'] | AnyHttpUrl = Field(
        default='all',
        title="CORS origin",
        description=(
            "Allows to specify origin for CORS. If set 'all' will set "
            "Access-Control-Allow-Origin to '*'; 'same-origin' return "
            "the same value as the 'Origin' request header."
            "A url may may be specified, restricting allowed origin to "
            "this url."
        ),
    )

    proxy_conf: bool = Field(
        default=False,
        title="Enable proxy_configuration",
        description=(
            "Indicates that the server is behind a reverse proxy. "
            "This enable handling of forwarded proxy headers"
        )
    )

    auth_tokens: List[str] = Field(
        default=[],
        description="List of authorized tokens",
    )

    def format_interface(self) -> str:
        match self.listen:
            case (address, port):
                return f"{address}:{port}"
            case socket:
                return socket


EXTERNAL_CONFIG_SECTION = "config_url"


@section(EXTERNAL_CONFIG_SECTION)
class ConfigUrl(Config):
    """
    Url for external configuration.
    The configuration is fetched from the remote url
    at startup and override all local settings.
    """
    ssl: Optional[SSLConfig] = None
    url: Optional[AnyHttpUrl] = Field(
        default=None,
        title="External configuration Url",
        description=(
            "Url to external configuration. "
            "The server will issue a GET method against this url at startup. "
            "The method should returns a valid configuration fragment. "
        ),
    )

    async def load_configuration(self) -> bool:
        if not self.url:
            return False

        import aiohttp

        if self.url.scheme == 'https':
            import ssl
            if self.ssl:
                ssl_context = ssl.create_default_context(cafile=self.ssl.ca)
                if self.ssl.cert:
                    ssl_context.load_cert_chain(self.ssl.cert, self.ssl.key)
            else:
                ssl_context = ssl.create_default_context()
        else:
            ssl_context = False  # No ssl validation

        async with aiohttp.ClientSession() as session:
            logger.info("Loading configuration from %s", self.url)
            async with session.get(str(self.url), ssl=ssl_context) as resp:
                cnf = await resp.json()
                logger.debug("Updating configuration:\n%s", cnf)
                confservice.update_config(cnf)

        return True
