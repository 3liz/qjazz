from py_qgis_contrib.core import config
from py_qgis_projects_cache.config import ProjectsConfig

from pydantic import (
    Field,
)
from typing_extensions import (
    List,
    Optional,
)

DEFAULT_INTERFACE = ("0.0.0.0", 23456)


class WorkerConfig(config.Config):
    name: str = Field(
        title="Name of the worker configuration",
    )
    projects: ProjectsConfig = Field(
        default=ProjectsConfig(),
        title="Projects configuration",
        description="Configuration du cache du projects",
    )
    interfaces: config.NetInterface = Field(
        default=[DEFAULT_INTERFACE],
        title="Interfaces to listen to",
    )
    ssl: Optional[config.SSLConfig] = Field(
        default=None,
        title="SSL/TLS configuration",
    )


@config.section("workspace")
class WorkespaceConfig(config.Config):
    workers: List[WorkerConfig] = Field(
        default=[WorkerConfig(name='default')],
        title="List of worker configuration",
        description=(
            "Configurations for workers. "
            "Each workers can be configured with a "
            "specific configuration."
        )
    )
