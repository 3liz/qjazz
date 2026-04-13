import sys

from pathlib import Path
from typing import (
    Literal,
    Optional,
    Protocol,
    TypeAlias,
    cast,
)

from pydantic import AnyHttpUrl, FilePath
from qjazz_core import logger
from qjazz_core.config import (
    ConfBuilder,
    ConfigBase,
    ConfigError,
    read_config_toml,
)
from qjazz_core.models import Field, Option

from .resolver import ChannelConfig

HttpCORS: TypeAlias = Literal["all", "same-origin"] | AnyHttpUrl


class Server(ConfigBase):
    address: str = Field(
        default="127.0.0.1:9080",
        title="Interfaces to listen to",
    )
    enable_tls: bool = Field(
        default=False,
        title="Use TLS",
    )
    tls_client_cafile: Option[FilePath] = Field(
        title="Client CA file",
        description="Certificat for client authentification",
    )
    tls_cert_file: Option[FilePath] = Field(
        title="TLS  key",
        description="Path to the TLS key file",
    )
    tls_key_file: Option[FilePath] = Field(
        title="SSL/TLS Certificat",
        description="Path to the TLS certificat file",
    )
    cross_origin: HttpCORS = Field(
        default="all",
        title="CORS origin",
        description="""
        Allows to specify origin for CORS. If set 'all' will set
        Access-Control-Allow-Origin to '*'; 'same-origin' return
        the same value as the 'Origin' request header.
        A url may may be specified, restricting allowed origin to
        this url.
        """,
    )
    num_workers: Option[int] = Field(
        title="Workers",
        description="Numbers of worker threads",
    )
    backends_request_timeout: int = Field(
        default=30,
        title="Request timeout",
    )
    shutdown_timeout: int = Field(
        default=30,
        title="Shutdown timeout",
        description="Shutdown grace period",
    )
    check_forwarded_headers: bool = Field(
        True,
        description="""
        Use forwarded connection infos request headers.
        This is required if your service is behind a reverse-proxy
        in order to ensure that the correct URL is used for links
        sent to the client.
        """,
    )


class ConfigProto(Protocol):
    logging: logger.LoggingConfig
    backends: dict[str, ChannelConfig]

    def model_dump_json(self, *args, **kwargs) -> str: ...


def create_config() -> ConfBuilder:
    builder = ConfBuilder()
    # `[Logging]` section
    builder.add_section("logging", logger.LoggingConfig)

    # Add the `[http]` configuration section
    builder.add_section("server", Server)

    # Add the `[backends]` configuration section
    builder.add_section(
        "backends",
        dict[str, ChannelConfig],
        field=Field(default={}),
    )

    return builder


#
# Configuration model builder
#

confservice = create_config()


#
# Load configuration file
#

BACKENDS_SECTION = "backends"


class BackendConfigError(Exception):
    def __init__(self, file, msg):
        super().__init__(f"Service configuration error in {file}: {msg}")


def load_configuration(configpath: Optional[Path]) -> ConfigProto:
    cnf = read_config_toml(configpath) if configpath else {}
    try:
        return cast("ConfigProto", confservice.validate(cnf))
    except ConfigError as err:
        print("Configuration error:", err, file=sys.stderr, flush=True)  # noqa T201
        sys.exit(1)
    except BackendConfigError as err:
        print(err, file=sys.stderr, flush=True)  # noqa T201
        sys.exit(1)
