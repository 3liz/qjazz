from pydantic import AnyHttpUrl, BeforeValidator, Field, Json
from typing_extensions import (
    Annotated,
    Dict,
    List,
    Optional,
    Protocol,
)

from py_qgis_cache.config import ProjectsConfig
from py_qgis_contrib.core import config, logger
from py_qgis_contrib.core.config import NetInterface, SSLConfig
from py_qgis_contrib.core.qgis import QgisPluginConfig

from .restore import CacheRestoreConfig

DEFAULT_INTERFACE = ("[::]", 23456)

#
# Service SSL configuration
#


class ListenConfig(config.ConfigBase):
    listen: NetInterface = Field(
        default=DEFAULT_INTERFACE,
        title="TCP:PORT interface or unix socket",
    )
    use_ssl: bool = False
    ssl: SSLConfig = SSLConfig()


def _validate_qgis_setting(value: str | bool | float | int) -> str:
    match value:
        case str():
            return value
        case float() | int():
            return str(value)
        case bool():
            return "true" if value else "false"
        case _:
            raise ValueError(f"Unsupported type for '{value}' (found '{type(value)}')")


QgisSettingValue = Annotated[str, BeforeValidator(_validate_qgis_setting)]


class WorkerConfig(config.ConfigBase):
    name: str = Field(
        default="default",
        title="Name of the worker instance",
    )
    description: str = Field(
        default="",
        title="Description",
        description="Description for administrative purpose",
    )
    projects: ProjectsConfig = Field(
        default=ProjectsConfig(),
        title="Projects configuration",
        description="Projects and cache configuration",
    )
    max_projects: int = Field(
        default=50,
        title="Max number of projects in cache",
        description=(
            "The maximum number of projects allowed in cache.\n"
            "The default value is set to 50 projects. "
        ),
    )
    load_project_on_request: bool = Field(
        default=True,
        title="Load project in cache when requested",
        description=(
            "Load project in cache at request.\n"
            "If set to 'false', project not loaded in cache will\n"
            "return a 403 HTTP code when requested.\n"
            "Thus, adding project's to cache will require a specific\n"
            "action from another service or admininstrative\n"
            "management tools."
        ),
    )
    reload_outdated_project_on_request: bool = Field(
        default=False,
        title="Reload outdated project when requested",
        description=(
            "Reload outdated project at request.\n"
            "If set to 'false', outdated project in cache will\n"
            "not be refreshed when requested.\n"
            "Thus, refreshing project's to cache will require a specific\n"
            "action from another service or admininstrative\n"
            "management tools."
        ),
    )
    plugins: QgisPluginConfig = Field(
        default=QgisPluginConfig(),
        title="Plugins configuration",
    )
    max_chunk_size: int = Field(
        default=1024 * 1024,
        title="Maximum chunk size",
        description="Set the maximum chunk size for streamed responses.",
    )
    interfaces: List[ListenConfig] = Field(
        default=[ListenConfig()],
        title="Interfaces to listen to",
        min_length=1,
    )
    max_waiting_requests: int = Field(
        default=20,
        title="Max number of concurrent requests",
        description=(
            "The maximum number of requests that can be\n"
            "queued for this worker task. If the number of\n"
            "waiting requests reach the limit, the subsequent\n"
            "requests will be returned with a `service unavailable`\n"
            "error"
        ),
    )
    process_timeout: int = Field(
        default=20,
        title="Stalled process timeout",
        description=(
            "Set the amount of time in seconds before considering\n"
            "considering that a process is stalled.\n"
            "A stalled process will be terminated and the server will\n"
            "exit with an error code"
        ),
    )
    shutdown_grace_period: int = Field(
        default=20,
        title="Shutdown grace period",
        description=(
            "The maximum amount of time to wait before\n"
            "closing connections. During this period,\n"
            "no new connections are allowed."
        ),
    )
    max_processes_failure_pressure: float = Field(
        default=0.,
        title="Max allowed processes failure ratio",
        description=(
            "The maximum ratio of terminated/initial processes\n"
            "allowed. If this limit is reached,  the server will\n"
            "issue a critical failure before exiting."
        ),
    )
    num_processes: int = Field(
        default=1,
        title="Number of Qgis processes",
        description=(
            "Set the number of Qgis processes per worker.\n"
            "If a processes crash, the worker is in a degraded\n"
            "state. When the last process exit the worker will\n"
            "stop with an error code.\n\n"
            "In order not to let the worker degrade itself slowly\n"
            "the number of worker should be kept low (from 1 to 3)\n"
            "or keep a relatively low 'max_processes_failure_pressure'.\n"
            "Note: server must be restarted if this option is modified."
        ),
    )
    rescale_period: int = Field(
        default=5,
        ge=0,
        title="Rescale period",
        description=(
            "Set the interval in seconds between rescaling of the number of\n"
            "live processes.\n"
            "Scaling will adjust the number of processes according \n"
            "to the configuration and dead processes will be replaced\n"
            "with new processes."
        ),
    )
    qgis_settings: Dict[str, QgisSettingValue] = Field(
        default={},
        title="Qgis settings",
        description=(
            "Qgis settings override.\n"
            "Use the syntax '<section>/<path>' for keys.\n"
            "Not that values defined here will override those\n"
            "from QGIS3.ini file."
        ),
    )


class RemoteConfigError(Exception):
    pass


class ConfigUrl(config.ConfigBase):
    (
        "Bootstrap configuration from remote location.\n"
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
            "The method should returns a valid configuration fragment."
        ),
    )

    def is_set(self) -> bool:
        return self.url is not None

    async def load_configuration(self) -> Optional[Json]:
        """ Load remote configuration and return the Json
            object
        """
        if not self.url:
            return None

        import aiohttp

        use_ssl = self.url.scheme == 'https'

        async with aiohttp.ClientSession() as session:
            logger.info("** Loading configuration from %s **", self.url)
            try:
                async with session.get(
                    str(self.url),
                    ssl=self.ssl.create_ssl_client_context() if use_ssl else False,
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        raise RemoteConfigError(
                            f"Failed to get configuration from {self.url} (error {resp.status})",
                        )
            except aiohttp.ClientConnectorSSLError as err:
                raise RemoteConfigError(str(err))


#
# Environment variables
#
ENV_CONFIGFILE = "PY_QGIS_WORKER_CONFIGFILE"


class ConfigProto(Protocol):
    logging: logger.LoggingConfig
    worker_config_url: ConfigUrl
    worker: WorkerConfig
    restore_cache: CacheRestoreConfig

    def model_dump_json(self, *args, **kwargs) -> str:
        ...


confservice = config.ConfBuilder()

confservice.add_section("worker", WorkerConfig)
confservice.add_section("worker_config_url", ConfigUrl)
confservice.add_section("restore_cache", ConfigUrl)

WORKER_SECTION = "worker"
