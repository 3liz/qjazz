from pydantic import AnyHttpUrl, Field, JsonValue
from typing_extensions import (
    Optional,
    Protocol,
)

from py_qgis_contrib.core import config, logger
from py_qgis_contrib.core.config import SSLConfig

from ._op_config import (
    WORKER_SECTION,
    ProjectsConfig,  # noqa F401
    WorkerConfig,
)
from .restore import CacheRestoreConfig


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

    async def load_configuration(self) -> Optional[JsonValue]:
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

confservice.add_section(WORKER_SECTION, WorkerConfig)
confservice.add_section("worker_config_url", ConfigUrl)
confservice.add_section("restore_cache", ConfigUrl)
