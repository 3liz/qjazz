#
from pydantic import Field

from py_qgis_contrib.core.config import ConfigBase, SSLConfig

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
        title="Allow only secure downloads",
        description="Only TLS encrypted downloads are allowed",
    )

    chunksize: int = Field(
        DEFAULT_CHUNKSIZE,
        ge=DEFAULT_CHUNKSIZE,
        title="Download chunksize",
    )

    ssl: SSLConfig = Field(
        default=SSLConfig(),
        title="TLS certifificats",
        description="Certificats required for TLS downloads connections",
    )

    download_url_expiration: int = Field(
        default=3600,
        title="Download url expiration",
        description="Download url expiration in seconds",
    )
