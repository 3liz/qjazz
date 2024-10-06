import asyncio
import os
import sys

from glob import glob
from pathlib import Path

from pydantic import AnyHttpUrl, Field
from typing_extensions import (
    Dict,
    Literal,
    Optional,
    Protocol,
    TypeAlias,
    cast,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import (
    ConfBuilder,
    ConfigBase,
    ConfigError,
    NetInterface,
    SSLConfig,
    config_version,
    read_config_toml,
)

from .metrics import MetricsConfig
from .resolver import BackendConfig
from .router import RouterConfig

DEFAULT_INTERFACE = ("127.0.0.1", 9080)


HttpCORS: TypeAlias = Literal['all', 'same-origin'] | AnyHttpUrl


class HttpConfig(ConfigBase):

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


DEFAULT_ADMIN_INTERFACE = ("127.0.0.1", 9876)


class AdminHttpConfig(HttpConfig):
    # Redefine net interface default
    listen: NetInterface = Field(
        default=DEFAULT_ADMIN_INTERFACE,
        title="Interfaces to listen to",
    )


DEFAULT_USER_AGENT = f"py-qgis-server2 middleware {config_version}"


class RemoteConfigError(Exception):
    pass


class ConfigUrl(ConfigBase):
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

    async def load_configuration(self, builder: ConfBuilder) -> bool:
        if not self.url:
            return False

        import aiohttp

        use_ssl = self.url.scheme == 'https'

        async with aiohttp.ClientSession() as session:
            logger.info("** Loading configuration from %s **", self.url)
            async with session.get(
                str(self.url),
                ssl=self.ssl.create_ssl_client_context() if use_ssl else False,
            ) as resp:
                if resp.status != 200:
                    raise RemoteConfigError(
                        f"Failed to get configuration from {self.url} (error {resp.status})",
                    )
                cnf = await resp.json()
                logger.trace("Loading configuration:\n%s", cnf)
                builder.update_config(cnf)

        return True


BACKENDS_SECTION = 'backends'


class ConfigProto(Protocol):
    logging: logger.LoggingConfig
    http: HttpConfig
    http_config_url: ConfigUrl
    admin_http: AdminHttpConfig
    router: RouterConfig
    metrics: Optional[MetricsConfig]
    backends: Dict[str, BackendConfig]
    includes: Optional[str]

    def model_dump_json(self, *args, **kwargs) -> str:
        ...


def create_config() -> ConfBuilder:

    builder = ConfBuilder()

    # Add the `[http]` configuration section
    builder.add_section('http', HttpConfig)
    builder.add_section("http_config_url", ConfigUrl)
    builder.add_section('admin_http', AdminHttpConfig)

    builder.add_section('router', RouterConfig)

    # Add the `[backends]` configuration section
    builder.add_section(
        BACKENDS_SECTION,
        Dict[str, BackendConfig],
        Field(default={}),
    )

    # Add the `[metrics]` optional configuration
    builder.add_section(
        'metrics',
        Optional[MetricsConfig],
        Field(
            default=None,
            title="Metrics configuration",
        ),
    )

    # Path to services configuration
    builder.add_section(
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

    return builder


#
# Configuration model builder
#

confservice = create_config()


#
# Load configuration file
#

# Environmemnt variables
ENV_CONFIGFILE = "QGIS_HTTP_CONFIGFILE"


class BackendConfigError(Exception):
    def __init__(self, file, msg):
        super().__init__(f"Service configuration error in {file}: {msg}")


def load_include_config_files(includes: str, conf: ConfigProto):
    """ Load extra services configuration files
    """
    for file in glob(includes):
        cnf = read_config_toml(Path(file))
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


def load_configuration(configpath: Optional[Path], verbose: bool = False) -> ConfigProto:

    if configpath:
        cnf = read_config_toml(configpath)
        os.environ[ENV_CONFIGFILE] = configpath.as_posix()
    else:
        cnf = {}
    try:
        conf = cast(ConfigProto, confservice.validate(cnf))

        # Load external configuration if requested
        # Do not load includes if configuration is remote
        if conf.http_config_url.is_set():
            print(
                f"** Loading initial config from {conf.http_config_url.url} **",
                file=sys.stderr,
                flush=True,
            )
            asyncio.run(conf.http_config_url.load_configuration(confservice))
            conf = cast(ConfigProto, confservice.conf)
        elif conf.includes:
            includes = conf.includes
            if configpath:
                # Includes must be relative to config file
                includes = str(configpath.joinpath(includes))
            load_include_config_files(includes, conf)

        if verbose:
            print(conf.model_dump_json(indent=4), file=sys.stderr, flush=True)

        log_level = logger.setup_log_handler(logger.LogLevel.TRACE if verbose else conf.logging.level)
        print("** Log level set to ", log_level.name, file=sys.stderr, flush=True)

        return confservice.conf

    except ConfigError as err:
        print("Configuration error:", err, file=sys.stderr, flush=True)
        sys.exit(1)
    except BackendConfigError as err:
        print(err, file=sys.stderr, flush=True)
        sys.exit(1)
