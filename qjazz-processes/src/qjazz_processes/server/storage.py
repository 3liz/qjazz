#
from pydantic import Field

from qjazz_contrib.core.config import ConfigBase, TLSConfig

# Config
#

DEFAULT_CHUNKSIZE = 1024 * 64


class StorageConfig(ConfigBase):
    """
    The storage configuration is used for configuring the
    connections to storage backends used by workers.
    """

    allow_insecure_connection: bool = Field(
        default=True,
        title="Allow insecure downloads",
        description="If set to false, only TLS encrypted downloads are allowed",
    )

    chunksize: int = Field(
        DEFAULT_CHUNKSIZE,
        ge=DEFAULT_CHUNKSIZE,
        title="Download chunksize",
    )

    tls: TLSConfig = Field(
        default=TLSConfig(),
        title="TLS certifificats",
        description="Certificats required for TLS downloads connections",
    )

    download_url_expiration: int = Field(
        default=3600,
        title="Download url expiration",
        description="Download url expiration in seconds",
    )
