from py_qgis_contrib.core import config
from py_qgis_contrib.core.qgis import QgisPluginConfig
from py_qgis_project_cache.config import ProjectsConfig

from pydantic import (
    Field,
)
from typing_extensions import (
    List,
)

DEFAULT_INTERFACE = ("[::]", 23456)


class WorkerConfig(config.Config):
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
            "The maximum number of projects allowed in cache. "
            "The default value is set to 50 projects. "
        )
    )
    load_project_on_request: bool = Field(
        default=True,
        title="Load project in cache when requested",
        description=(
            "Load project in cache at request. "
            "If set to 'false', project not loaded in cache will "
            "return a 403 HTTP code when requested. "
            "Thus, adding project's to cache will require a specific "
            "action from another service or admininstrative "
            "management tools."
        )
    )
    reload_outdated_project_on_request: bool = Field(
        default=False,
        title="Reload outdated project when requested",
        description=(
            "Reload outdated project at request. "
            "If set to 'false', outdated project in cache will "
            "not be refreshed when requested. "
            "Thus, refreshing project's to cache will require a specific "
            "action from another service or admininstrative "
            "management tools."
        )
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
    listen: List[config.NetInterface] = Field(
        default=[DEFAULT_INTERFACE],
        title="Interfaces to listen to",
        min_length=1,
    )
    max_waiting_requests: int = Field(
        default=20,
        title="Max number of concurrent requests",
        description=(
            "The maximum number of requests that can be "
            "queued for this worker task. If the number of "
            "waiting requests reach the limit, the subsequent "
            "requests will be returned with a `service unavailable` "
            "error"
        ),
    )
    worker_timeout: int = Field(
        default=20,
        title="Stalled worker timeout",
        description=(
            "Set the amount of time in seconds before considering "
            "considering that the worker is stalled. "
            "A stalled worker will be terminated and the server will "
            "exit with an error code"
        ),
    )
    shutdown_grace_period: int = Field(
        default=20,
        title="Shutdown grace period",
        description=(
            "The maximum amount of time to wait before "
            "closing connections. During this period, "
            "no new connections are allowed."
        ),
    )
    max_worker_failure_pressure: float = Field(
        default=0.,
        title="Max worker failure pressure",
        description=(
            "The maximum ratio of terminated/initial workers "
            "allowed. If this limit is reached,  the server will "
            "issue a critical failure before exiting."
        ),
    )
