import os

from typing import Annotated

from pydantic import (
    AfterValidator,
    BeforeValidator,
)

from qjazz_cache.config import ProjectsConfig
from qjazz_contrib.core import config
from qjazz_contrib.core.models import Field
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
QgisSettingValues = dict[str, QgisSettingValue]


def validate_qgis_settings(settings: QgisSettingValues) -> QgisSettingValues:
    # Define where QGIS store network cache, by default it is
    # in ~/.cache/QGIS/.... make it configurable from env.
    net_cache_dir = os.getenv("QGIS_NETWORK_CACHE_DIRECTORY")
    if net_cache_dir:
        settings["cache/directory"] = net_cache_dir
    # Cache size in kilobytes
    net_cache_size = os.getenv("QGIS_NETWORK_CACHE_SIZE_KB")
    if net_cache_size:
        settings["cache/size-bytes"] = str(int(net_cache_size) * 1024)
    return settings


def static_api_aliases(aliases: dict[str, str]) -> dict[str, str]:
    # Add static api aliases definitions
    from .delegate import API_ALIASES

    api_aliases = API_ALIASES.copy()
    api_aliases.update((k.upper(),v) for k, v in aliases.items())
    return api_aliases


class QgisConfig(config.ConfigBase):
    projects: ProjectsConfig = Field(
        default=ProjectsConfig(),
        title="Projects configuration",
        description="Projects and cache configuration",
    )
    max_projects: int = Field(
        default=50,
        title="Max number of projects in cache",
        description="""
        The maximum number of projects allowed in cache.\nThe default value is set to 50 projects.
        """,
    )
    load_project_on_request: bool = Field(
        default=True,
        title="Load project in cache when requested",
        description="""
        Load project in cache at request.
        If set to 'false', project not loaded in cache will
        return a 403 HTTP code when requested.
        Thus, adding project's to cache will require a specific
        action from another service or admininstrative
        management tools.
        """,
    )
    reload_outdated_project_on_request: bool = Field(
        default=True,
        title="Reload outdated project when requested",
        description="""
        Reload outdated project at request.
        If set to 'false', outdated project in cache will
        not be refreshed when requested.
        Thus, refreshing project's to cache will require a specific
        action from another service or admininstrative
        management tools.
        """,
    )
    enable_python_embedded: bool = Field(
        default=False,
        title="Allow python embedded macros",
        description="""
        Set authorization to run Python Embedded in projects.
        If enabled, it will use the QGIS settings value defined in the
        QGIS settings options.
        If disabled, Python Embedded is completely disabled and QGIS defined
        settings will be ignored.
        For security reason this is disabled by default.
        """,
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
    qgis_settings: Annotated[
        QgisSettingValues,
        AfterValidator(validate_qgis_settings),
    ] = Field(
        default={},
        validate_default=True,
        title="Qgis settings",
        description="""
        Qgis settings override.
        Use the syntax '<section>/<path>' for keys.
        Not that values defined here will override those
        from QGIS3.ini file.
        """,
    )
    ignore_interrupt_signal: bool = Field(
        True,
        title="Ignore INT signal in worker",
        description="""
        Ignore INT signal in workers.
        This is useful when you don't want
        propagating signal from parent process.
        """,
    )
    network: QgisNetworkConfig = Field(
        QgisNetworkConfig(),
        title="QGIS Network configuration",
    )
    use_default_server_handler: bool = Field(
        False,
        title="Use default QGIS server handler",
        description="""
        Use the default QGIS server handler instead
        tf the alternative QJazz optimized handler.
        Note that the QJazz handler deactivate the
        'onSendResponse' method. If your plugin's filters
        require the 'onSendResponse' method, then you
        must set this option to true.
        """,
    )
    api_aliases: Annotated[
        dict[str,str],
        AfterValidator(static_api_aliases),
    ] = Field(
        {},
        validate_default=True,
        title="API aliases",
        description="""
        Use aliases for QGIS server apis.
        """,
    )
