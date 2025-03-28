from typing import Annotated

from pydantic import BeforeValidator, Field

from qjazz_cache.config import ProjectsConfig
from qjazz_contrib.core import config
from qjazz_contrib.core.qgis import QgisNetworkConfig, QgisPluginConfig


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


class QgisConfig(config.ConfigBase):
    projects: ProjectsConfig = Field(
        default=ProjectsConfig(),
        title="Projects configuration",
        description="Projects and cache configuration",
    )
    max_projects: int = Field(
        default=50,
        title="Max number of projects in cache",
        description=("The maximum number of projects allowed in cache.\nThe default value is set to 50 projects. "),
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
    enable_python_embedded: bool = Field(
        default=False,
        title="Allow python embedded macros",
        description=(
            "Set authorization to run Python Embedded in projects.\n"
            "If enabled, it will use the QGIS settings value defined in the\n"
            "QGIS settings options.\n"
            "If disabled, Python Embedded is completely disabled and QGIS defined\n"
            "settings will be ignored.\n"
            "For security reason this is disabled by default."
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
    qgis_settings: dict[str, QgisSettingValue] = Field(
        default={},
        title="Qgis settings",
        description=(
            "Qgis settings override.\n"
            "Use the syntax '<section>/<path>' for keys.\n"
            "Not that values defined here will override those\n"
            "from QGIS3.ini file."
        ),
    )
    ignore_interrupt_signal: bool = Field(
        True,
        title="Ignore INT signal in worker",
        description=(
            "Ignore INT signal in workers.\nThis is useful when you don't want\npropagating signal from parent process."
        ),
    )
    network: QgisNetworkConfig = Field(
        QgisNetworkConfig(),
        title="QGIS Network configuration",
    )
