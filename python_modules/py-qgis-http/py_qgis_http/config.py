import sys

from pathlib import Path
from glob import glob
from pydantic import (
    Field,
    AnyHttpUrl,
    AfterValidator,
)
from typing_extensions import (
    Optional,
    Dict,
    Literal,
    Annotated,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import (
    Config,
    ConfigService,
    SSLConfig,
    NetInterface,
    ConfigError,
    read_config_toml,
    confservice,
)

from .resolver import BackendConfig  # noqa

DEFAULT_INTERFACE = ("0.0.0.0", 8080)


def _check_ssl_config(sslconf):
    match (sslconf.key, sslconf.cert):
        case (str(), None):
            raise ValueError("Missing ssl cert file")
        case (None, str()):
            raise ValueError("Missinc ssl key file")
    return sslconf


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

    def format_interface(self) -> str:
        match self.listen:
            case (address, port):
                return f"{address}:{port}"
            case socket:
                return socket


HTTP_SECTION = 'http'
BACKENDS_SECTION = 'backends'


def add_configuration_sections(service: Optional[ConfigService] = None):
    # Add the `[http]` configuration section
    service = service or confservice
    service.add_section(HTTP_SECTION, HttpConfig)

    # Add the `[backends]` configuration section
    service.add_section(
        BACKENDS_SECTION,
        (Dict[str, BackendConfig], Field(default={})),
    )

    # Path to services configuration
    service.add_section(
        'includes',
        (
            Optional[str],
            Field(
                default=None,
                title="Path or globbing to services configuration files",
            )
        )
    )

#
# Load configuration file
#


class BackendConfigError(Exception):
    def __init__(file, msg):
        super().__init__(f"Service configuration error in {file}: {msg}")


def load_configuration(configpath: Optional[Path]) -> Config:

    if configpath:
        cnf = read_config_toml(
            configpath,
            location=str(configpath.parent.absolute())
        )
    else:
        cnf = {}
    try:
        confservice.validate(cnf)
        conf = confservice.conf

        # Load extra services configuration files
        if conf.includes:
            for file in glob(conf.includes):
                cnf = read_config_toml(file)
                if BACKENDS_SECTION not in cnf:
                    logger.debug("No 'services' section in %s", file)
                    continue
                backends = cnf[BACKENDS_SECTION]
                if not isinstance(backends, dict):
                    raise BackendConfigError(file, "Invalid backends section")
                for (name, _backend) in backends.items():
                    if name in cnf.backends:
                        raise BackendConfigError(
                            file,
                            f"service {name} already defined",
                        )
                    cnf.backends[name] = BackendConfig.model_validate(_backend)
        return conf
    except ConfigError as err:
        print("Configuration error:", err, file=sys.stderr)
        sys.exit(1)
    except BackendConfigError as err:
        print(err, file=sys.stderr)
        sys.exit(1)
