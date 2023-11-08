import os
import sys
import json
import asyncio

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
    section,
)

from .resolver import BackendConfig  # noqa

DEFAULT_INTERFACE = ("0.0.0.0", 80)


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


EXTERNAL_CONFIG_SECTION = "config_url"

DEFAULT_USER_AGENT = f"py-qgis-server2 middleware {confservice.version}"


class RemoteConfigError(Exception):
    pass


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

        if self.url.scheme == 'https':
            import ssl
            if self.ssl:
                ssl_context = ssl.create_default_context(cafile=self.ssl.ca)
                if self.ssl.cert:
                    ssl_context.load_cert_chain(self.ssl.cert, self.ssl.key)
            else:
                ssl_context = ssl.create_default_context()
        else:
            ssl_context = None

        client = httpclient.AsyncHTTPClient(
            force_instance=True,
            defaults=dict(
                user_agent=self.user_agent,
                ssl_options=ssl_context,
            )
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


# Environmemnt variables
ENV_CONFIGFILE = "QGIS_HTTP_CONFIGFILE"


class BackendConfigError(Exception):
    def __init__(file, msg):
        super().__init__(f"Service configuration error in {file}: {msg}")


def load_configuration(configpath: Optional[Path], verbose: bool = False) -> Config:

    if configpath:
        cnf = read_config_toml(
            configpath,
            location=str(configpath.parent.absolute())
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
            print(f"** Loading initial config from {conf.config_url.url} **", flush=True)
            asyncio.run(conf.config_url.load_configuration())
        elif conf.includes:
            # Load extra services configuration files
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

        conf = confservice.conf
        if verbose:
            print(conf.model_dump_json(indent=4), flush=True)

        log_level = logger.setup_log_handler(logger.LogLevel.TRACE if verbose else None)
        print("** Log level set to ", log_level.name, flush=True)

        return conf

    except ConfigError as err:
        print("Configuration error:", err, file=sys.stderr, flush=True)
        sys.exit(1)
    except BackendConfigError as err:
        print(err, file=sys.stderr, flush=True)
        sys.exit(1)
