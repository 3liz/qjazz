
from pydantic import (
    Field,
)
from typing_extensions import (
    Optional,
    List,
)


from py_qgis_contrib.core import config

from .resolver import BackendConfig

DEFAULT_INTERFACE = ("0.0.0.0", 8080)


# Return a ChannelCredential struct
def channel_credentials(files: config.SSLConfig):
    def _read(f) -> Optional[bytes]:
        if f:
            with Path(f).open('rb') as fp:
                return fp.read()

    return grpc.ssl_channel_credentials(
        root_certificate=_read(files.ca),
        certificate=_read(files.cert),
        private_key=_read(files.key),
    )


class HttpConfig(config.Config):
 
    listen: config.NetInterface = Field(
        default=DEFAULT_INTERFACE,
        title="Interfaces to listen to",
    )
    use_ssl: bool = Field(
        default=False,
        title="Use ssl",
    )
    ssl: SSLConfig = Field(
        default=SSLConfig(),
        title="SSL configuration",
    )
    cross_origin: bool = Field(
        default=True,
        Title="Allow CORS",
        description=(
            "Allows any origin for CORS. If set to false, "
            "allow only CORS for the 'Origin' header."
        )
    )


class ServicesConfig(config.Config):
    upstream: List[BackendConfig] = Field(
        title="Backend Services",
    )



