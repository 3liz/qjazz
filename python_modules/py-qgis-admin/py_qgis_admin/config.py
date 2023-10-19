from pydantic import (
    AfterValidator,
    Field,
    AnyHttpUrl,
)

from typing_extensions import (
    Annotated,
    Literal,
    List,
)

from py_qgis_contrib.core.config import (
    Config,
    SSLConfig,
    NetInterface,
    section,
)


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
        )
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
        Field(
            default=[],
            description="List of authorized tokens",
        )
    )

    def format_interface(self) -> str:
        match self.listen:
            case (address, port):
                return f"{address}:{port}"
            case socket:
                return socket
