import asyncio
import json
import os
import sys

from glob import glob
from pathlib import Path

from pydantic import AnyHttpUrl, Field
from typing_extensions import Any, Dict, Literal, Optional, TypeAlias

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import (
    Config,
    ConfigError,
    ConfigService,
    NetInterface,
    SSLConfig,
    confservice,
    read_config_toml,
    section,
)

from . import metrics
from .resolver import BackendConfig

DEFAULT_INTERFACE = ("0.0.0.0", 80)


HttpCORS: TypeAlias = Literal['all', 'same-origin'] | AnyHttpUrl


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
        title="SSL configuration",
    )
    cross_origin: HttpCORS = Field(
        default='all',
        title="CORS origin",
        description=(
            "Allows to specify origin for CORS. If set 'all' will set\n"
            "Access-Control-Allow-Origin to '*'; 'same-origin' return\n"
            "the same value as the 'Origin' request header.\n"
            "A url may may be specified, restricting allowed origin to\n"
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

    def format_interface(self) -> str:
        match self.listen:
            case (address, port):
                return f"{address}:{port}"
            case socket:
                return str(socket)


DEFAULT_ADMIN_INTERFACE = ("0.0.0.0", 9876)


class AdminHttpConfig(HttpConfig):
    # Redefine net interface default
    listen: NetInterface = Field(
        default=DEFAULT_ADMIN_INTERFACE,
        title="Interfaces to listen to",
    )


EXTERNAL_CONFIG_SECTION = "config_url"

DEFAULT_USER_AGENT = f"py-qgis-server2 middleware {confservice.version}"


class RemoteConfigError(Exception):
    pass


@section(EXTERNAL_CONFIG_SECTION)
class ConfigUrl(Config):
    (
        "Url for external configuration.\n"
        "The configuration is fetched from the remote url\n"
        "at startup and override all local settings."
    )
    ssl: SSLConfig = SSLConfig()
    url: Optional[AnyHttpUrl] = Field(
        default=None,
        title="External configuration Url",
        description=(
            "Url to external configuration.\n"
            "The server will issue a GET method against this url at startup.\n"
            "The method should returns a valid configuration fragment.\n"
        ),
    )

    user_agent: str = Field(
        default=DEFAULT_USER_AGENT,
        title="User agent",
        description="The user agent for configuration requests",
    )

    def is_set(self) -> bool:
        return self.url is not None

    async def load_configuration(self) -> bool:
        if not self.url:
            return False

        from tornado import httpclient

        use_ssl = self.url.scheme == 'https'

        client = httpclient.AsyncHTTPClient(
            force_instance=True,
            defaults=dict(
                user_agent=self.user_agent,
                ssl_options=self.ssl.create_ssl_client_context() if use_ssl else None,
            ),
        )

        try:
            logger.info("** Loading configuration from %s **", self.url)
            resp = await client.fetch(str(self.url))
            if resp.code == 200:
                cnf = json.loads(resp.body)
                logger.debug("Updating configuration:\n%s", cnf)
                confservice.update_config(cnf)
        except (json.JSONDecodeError, ConfigError) as err:
            raise RemoteConfigError(f"Invalid configuration: {err}") from None
        except httpclient.HTTPError as err:
            raise RemoteConfigError(
                f"Failed to get configuration from {self.url} (error {err.code})",
            ) from None
        finally:
            client.close()

        return True


HTTP_SECTION = 'http'
BACKENDS_SECTION = 'backends'
ADMIN_SERVER_SECTION = 'admin_server'


def add_configuration_sections(service: Optional[ConfigService] = None):
    # Add the `[http]` configuration section
    service = service or confservice
    service.add_section(HTTP_SECTION, HttpConfig)
    service.add_section(ADMIN_SERVER_SECTION, AdminHttpConfig)

    # Add the `[backends]` configuration section
    service.add_section(
        BACKENDS_SECTION,
        Dict[str, BackendConfig],
        Field(default={}),
    )

    # Add the `[metrics]` optional configuration
    service.add_section(
        'metrics',
        Optional[metrics.MetricConfig],
        Field(
            default=None,
            title="Metrics configuration",
        ),
    )

    # Path to services configuration
    service.add_section(
        'includes',
        Optional[str],
        Field(
            default=None,
            title="Path to services configuration files",
            description=(
                "Path or globbing to services configuration files.\n"
                "Note that this section is ignored if remote configuration\n"
                "is used."
            ),
        ),
    )

#
# Load configuration file
#


# Environmemnt variables
ENV_CONFIGFILE = "QGIS_HTTP_CONFIGFILE"


class BackendConfigError(Exception):
    def __init__(self, file, msg):
        super().__init__(f"Service configuration error in {file}: {msg}")


def load_include_config_files(conf: Config):
    """ Load extra services configuration files
    """
    conf: Any = conf

    for file in glob(conf.includes):
        cnf = read_config_toml(file)
        if BACKENDS_SECTION not in cnf:
            logger.debug("No 'services' section in %s", file)
            continue
        backends = cnf[BACKENDS_SECTION]
        if not isinstance(backends, dict):
            raise BackendConfigError(file, "Invalid backends section")
        for (name, _backend) in backends.items():
            if name in conf.backends:
                raise BackendConfigError(
                    file,
                    f"service {name} already defined",
                )
            conf.backends[name] = BackendConfig.model_validate(_backend)


def load_configuration(configpath: Optional[Path], verbose: bool = False) -> Config:

    if configpath:
        cnf = read_config_toml(
            configpath,
            location=str(configpath.parent.absolute()),
        )
        os.environ[ENV_CONFIGFILE] = configpath.as_posix()
    else:
        cnf = {}
    try:
        confservice.validate(cnf)
        conf = confservice.conf

        # Load external configuration if requested
        # Do not load includes if configuration is remote
        if conf.config_url.is_set():
            print(f"** Loading initial config from {conf.config_url.url} **", file=sys.stderr, flush=True)
            asyncio.run(conf.config_url.load_configuration())
            conf = confservice.conf
        elif conf.includes:
            load_include_config_files(conf)

        if verbose:
            print(conf.model_dump_json(indent=4), file=sys.stderr, flush=True)

        log_level = logger.setup_log_handler(logger.LogLevel.TRACE if verbose else None)
        print("** Log level set to ", log_level.name, file=sys.stderr, flush=True)

        return conf

    except ConfigError as err:
        print("Configuration error:", err, file=sys.stderr, flush=True)
        sys.exit(1)
    except BackendConfigError as err:
        print(err, file=sys.stderr, flush=True)
        sys.exit(1)
