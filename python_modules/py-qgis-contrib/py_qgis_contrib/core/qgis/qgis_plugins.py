#
# Copyright 2018-2023 3liz
# Author David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

""" Qgis server plugin managment

"""
import sys
import os
import configparser
import traceback

from pydantic import (
    Field,
    ValidationInfo,
    AfterValidator,
)

from dataclasses import dataclass

from pathlib import Path
from typing_extensions import (
    Optional,
    Iterator,
    Dict,
    List,
    Any,
    Annotated,
    assert_never,
)

from enum import Enum

from .. import logger
from .. import componentmanager
from .. import config


class PluginError(Exception):
    pass


class PluginType(Enum):
    PROCESSING = "processing"
    SERVER = "server"


QGIS_PLUGIN_SERVICE_CONTRACTID = '@3liz.org/qgis-plugin-service;1'


def _validate_plugins_paths(paths: List[Path], _: ValidationInfo) -> List[Path]:
    if not paths and os.getenv("QGIS_PLUGINPATH"):
        paths = [Path(p) for p in os.getenv("QGIS_PLUGINPATH").split(":")]
    for path in paths:
        if not path.exists() or not path.is_dir():
            print(f"WARNING: '{path}' is not a valid plugin directory")
    return paths


class QgisPluginConfig(config.Config):
    paths: Annotated[
        List[Path],
        AfterValidator(_validate_plugins_paths),
    ] = Field(
        default=[],
        title="Plugin paths",
        description=(
            "List of search paths for plugins. "
            "All Qgis plugins found will be loaded "
            "if they are compatible with the current "
            "Qgis version."
        ),
    )


@dataclass(frozen=True)
class Plugin:
    name: str
    path: Path
    plugin_type: PluginType
    init: Any

    @property
    def metadata(self) -> Optional[Dict]:
        """ Return plugin metadata
        """
        # Read metadata
        metadatafile = self.path / 'metadata.txt'
        if not metadatafile.exists():
            return

        with metadatafile.open(mode='rt') as f:
            cp = configparser.ConfigParser()
            cp.read_file(f)
            metadata = {s: dict(p.items()) for s, p in cp.items()}
            metadata.pop('DEFAULT', None)
            return metadata


class QgisPluginService:
    """ Manage qgis plugins
    """

    def __init__(self, config: QgisPluginConfig) -> None:
        self._config = config
        self._plugins = {}
        self._providers: List[str] = []

    @property
    def plugins(self) -> Iterator[Plugin]:
        return (p for p in self._plugins.values())

    @property
    def num_plugins(self) -> int:
        return len(self._plugins)

    def register_as_service(self):
        componentmanager.register_service(QGIS_PLUGIN_SERVICE_CONTRACTID, self)

    def load_plugins(self, plugin_type: PluginType, interface: Optional['QgsServerInterface']):  # noqa F821
        """ Load all plugins found
        """
        if plugin_type == PluginType.PROCESSING:
            from .processing import ProcessesLoader
            processes = ProcessesLoader(self._providers)

        for plugin_path in self._config.paths:

            sys.path.append(str(plugin_path))

            if plugin_type == PluginType.PROCESSING:
                processes.read_configuration(plugin_path)

            for plugin in find_plugins(plugin_path, plugin_type):
                # noinspection PyBroadException
                try:
                    if plugin in sys.modules:
                        # Take care of module conflicts
                        raise PluginError(
                            f"The module '{plugin}' in '{plugin_path}' conflict with "
                            f"a previously loaded module: {sys.modules[plugin].__file__}"
                        )

                    __import__(plugin)

                    package = sys.modules[plugin]

                    # Initialize the plugin
                    match plugin_type:
                        case PluginType.SERVER:
                            init = package.serverClassFactory(interface)
                        case PluginType.PROCESSING:
                            init = processes.init_processing(package)
                        case _ as unreachable:
                            assert_never(unreachable)

                    self._plugins[plugin] = Plugin(
                        name=plugin,
                        path=Path(package.__file__).parent,
                        plugin_type=plugin_type,
                        init=init,
                    )
                    logger.info(f"Loaded plugin {plugin}")
                except Exception:
                    raise PluginError(
                        f"Error loading plugin '{plugin}':\n{traceback.format_exc()}"
                    ) from None

    @property
    def providers(self) -> Iterator['QgsProcessingProvider']:  # noqa F821
        """ Return published providers
        """
        from qgis.core import QgsApplication
        reg = QgsApplication.processingRegistry()
        return (reg.providerById(_id) for _id in self._providers)


def find_plugins(path: str, plugin_type: PluginType) -> Iterator[str]:
    """ return list of plugins in given path
    """
    path = Path(path)
    for plugin in path.glob("*"):
        logger.debug(f"Looking for plugin in '{plugin}'")

        if not plugin.is_dir():
            # Warn about dangling symlink
            # This occurs when running in docker container
            # and symlink target path are not visible from the
            # container - give some hint for debugging
            if plugin.is_symlink():
                logger.warning(f"*** The symbolic link '{plugin}' is not resolved."
                               " If you are running in docker container please consider"
                               "mounting the target path in the container.")
            continue

        metadata_file = plugin / 'metadata.txt'
        if not metadata_file.exists():
            # Do not log here
            continue

        if not (plugin / '__init__.py').exists():
            logger.warning(f"'{plugin}' : Found metadata file but no Python entry point !")
            continue

        cp = configparser.ConfigParser()

        try:
            with metadata_file.open(mode='rt') as f:
                cp.read_file(f)

            general = cp['general']

            match plugin_type:
                case PluginType.SERVER:
                    if not general.getboolean('server'):
                        logger.warning(f"'{plugin}' is not a server plugin")
                        continue
                case PluginType.PROCESSING:
                    if not general.getboolean('hasProcessingProvider'):
                        logger.warning(f"'{plugin}' is not a processing plugin")
                        continue
                case _:
                    continue

            min_ver = general.get('qgisMinimumVersion')
            max_ver = general.get('qgisMaximumVersion')

        except Exception as exc:
            logger.error(f"'{plugin}' : Error reading plugin metadata '{metadata_file}': {exc}")
            continue

        if not checkQgisVersion(min_ver, max_ver):
            logger.warning(f"Unsupported version for plugin '{plugin}'. Discarding")
            continue

        yield plugin.name


def checkQgisVersion(minver: str, maxver: str) -> bool:
    from qgis.core import Qgis

    def to_int(ver):
        major, *ver = ver.split('.')
        major = int(major)
        minor = int(ver[0]) if len(ver) > 0 else 0
        rev = int(ver[1]) if len(ver) > 1 else 0
        if minor >= 99:
            minor = rev = 0
            major += 1
        if rev > 99:
            rev = 99
        return int(f"{major:d}{minor:02d}{rev:02d}")

    version = to_int(Qgis.QGIS_VERSION.split('-')[0])
    minver = to_int(minver) if minver else version
    maxver = to_int(maxver) if maxver else version

    return minver <= version <= maxver
