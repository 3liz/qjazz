import os

from pathlib import Path

from pydantic import PositiveInt, SecretStr
from qjazz_core import config
from qjazz_core.models import Field, Option


class StoreConfig(config.ConfigBase):
    endpoint: str = Field(
        default="localhost:9000",
        title="S3/Minio endpoint",
    )

    cafile: Option[Path] = None

    access_key: SecretStr
    secret_key: SecretStr

    enable_tls: bool = Field(False, title="Enable TLS")
    check_certificat: bool = Field(True, title="Check certificat")

    region: Option[str] = None

    access_ttl: PositiveInt = Field(
        default=43200,
        title="Access TTL",
        description="""
        Lifetime in seconds given to a job store access since the job
        was scheduled for execution; the access credentials will no be
        longer valid after this time.
        The minimum lifetime is 900s, and the store backend may cap
        the lifetime (e.g. 12h for RustFS and AWS).
        """,
    )

    def configure_store(self):
        if self.cafile:
            # Required for Minio client"
            os.environ["SSL_CERT_FILE"] = str(self.cafile)
