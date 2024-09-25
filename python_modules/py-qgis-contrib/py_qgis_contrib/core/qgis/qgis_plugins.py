#
# Copyright 2018-2023 3liz
# Author David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

""" Qgis server plugin managment

"""
import configparser
import os
import sys
import traceback

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pydantic import (
    AfterValidator,
    Field,
    JsonValue,
    ValidationInfo,
)
from typing_extensions import (
    Annotated,
    Any,
    Dict,
    Iterator,
    List,
    Literal,
    Optional,
    Self,
    Set,
    Tuple,
    Type,
    assert_never,
    cast,
)

import qgis

from .. import componentmanager, config, logger
from ..condition import assert_precondition
from .processing import BuiltinProviderSet


class PluginError(Exception):
    pass


class PluginType(Enum):
    PROCESSING = "processing"
    SERVER = "server"


QGIS_PLUGIN_SERVICE_CONTRACTID = '@3liz.org/qgis-plugin-service;1'


def _default_plugin_path() -> Path:
    """ Return the default plugin's path
    """
    return Path(
        os.getenv('QGIS_OPTIONS_PATH')
        or os.getenv('QGIS_CUSTOM_CONFIG_PATH')
        or os.getenv('QGIS_HOME')
        or Path.home().joinpath('.qgis-server'),
        'plugins',
    )


def _validate_plugins_paths(paths: List[Path], _: ValidationInfo) -> List[Path]:
    if not paths:
        path_env = os.getenv("QGIS_PLUGINPATH")
        if path_env:
            paths = [Path(p) for p in path_env.split(":")]
    paths.append(_default_plugin_path())
    for path in paths:
        if not path.exists() or not path.is_dir():
            print(   # noqa T201
                f"WARNING: '{path}' is not a valid plugin directory",
                file=sys.stderr,
                flush=True,
            )
    return paths


class QgisPluginConfig(config.ConfigBase):
    paths: Annotated[
        List[Path],
        AfterValidator(_validate_plugins_paths),
    ] = Field(
        default=[],
        validate_default=True,
        title="Plugin paths",
        description=(
            "The list of search paths for plugins.\n"
            "Qgis plugins found will be loaded according to\n"
            "the 'install' list.\n"
            "If the list is empty, the 'QGIS_PLUGINPATH'\n"
            "variable will be checked."
        ),
    )
    install: Optional[Set[str]] = Field(
        default=None,
        title="Installable plugins",
        description=(
            "The list of installable plugins.\n"
            "Note: if the plugin directory contains other plugins\n"
            "plugins not in the list will NOT be loaded !\n"
            "The Plugins will be installed at startup\n"
            "if the 'install_mode' is set to 'auto'.\n"
            "Note that an empty list means what it is:\n"
            "i.e, *no* installed plugins."
        ),
    )
    install_mode: Literal['auto', 'external'] = Field(
        default='external',
        title='Plugin installation mode',
        description=(
            "If set to 'auto', plugins installation\n"
            "will be checked at startup. Otherwise,\n"
            "Installation will be done from already available\n"
            "plugins."
        ),
    )
    enable_scripts: bool = Field(
        default=True,
        title="Enable processing scripts",
        description="Enable publication of processing scripts",
    )
    extra_builtin_providers: BuiltinProviderSet = Field(
        default=set(),
        title="Extra builtins providers",
        description=(
            "Load extra builtin processing providers\n"
            "such as 'grass' and 'otb'."
        ),
    )
    plugin_manager: Path = Field(
        default=Path("/usr/local/bin/qgis-plugin-manager"),
        title="Path to plugin manager executable",
        description=(
            "The absolute path to the qgis-plugin_manager executable\n"
            "that will be used for installing plugin in automatic mode."
        ),
    )

    def do_install(self):
        if self.install_mode == 'auto':
            install_plugins(self)


JsonDict = Dict[str, JsonValue]


@dataclass(frozen=True)
class Plugin:
    name: str
    path: Path
    plugin_type: PluginType
    init: Any

    @property
    def metadata(self) -> JsonDict:
        """ Return plugin metadata
        """
        # Read metadata
        metadatafile = self.path / 'metadata.txt'
        if not metadatafile.exists():
            return {}

        with metadatafile.open(mode='rt') as f:
            cp = configparser.ConfigParser()
            cp.read_file(f)
            metadata = {s: dict(p.items()) for s, p in cp.items()}
            metadata.pop('DEFAULT', None)
            return cast(JsonDict, metadata)


class QgisPluginService:
    """ Manage qgis plugins
    """

    def __init__(self, config: QgisPluginConfig) -> None:
        self._config = config
        self._plugins: Dict[str, Plugin] = {}
        self._providers: List[str] = []

    @property
    def plugins(self) -> Iterator[Plugin]:
        return (p for p in self._plugins.values())

    @property
    def num_plugins(self) -> int:
        return len(self._plugins)

    def register_as_service(self):
        componentmanager.register_service(QGIS_PLUGIN_SERVICE_CONTRACTID, self)

    @classmethod
    def get_service(cls: Type[Self]) -> Self:
        """ Return QgisPluginService instance as a service.
            This require that register_as_service has been called
            in the current context
        """
        return componentmanager.get_service(QGIS_PLUGIN_SERVICE_CONTRACTID)

    def load_plugins(self, plugin_type: PluginType, interface: Optional['qgis.server.QgsServerInterface']):
        """ Load all plugins found
        """
        if plugin_type == PluginType.PROCESSING:
            from .processing import ProcessesLoader
            processes = ProcessesLoader(self._providers, allow_scripts=self._config.enable_scripts)
            # Load extra builtins
            extras = self._config.extra_builtin_providers
            if extras:
                self._BUILTIN_PROVIDERS = processes.load_builtin_providers(extras)

        white_list = self._config.install

        for plugin_path in self._config.paths:

            sys.path.append(str(plugin_path))

            if plugin_type == PluginType.PROCESSING:
                processes.read_configuration(plugin_path)

            for plugin, meta in find_plugins(plugin_path, plugin_type):
                # noinspection PyBroadException
                try:
                    # Check white list
                    name = meta['general']['name']
                    if white_list is not None and name not in white_list:
                        continue

                    if plugin in sys.modules:
                        # Take care of module conflicts
                        raise PluginError(
                            f"The module '{plugin}' in '{plugin_path}' conflict with "
                            f"a previously loaded module: {sys.modules[plugin].__file__}",
                        )

                    __import__(plugin)

                    package = sys.modules[plugin]

                    # Mark packace as loaded by py_qgis_server
                    # allow plugins to check if it has been
                    # loaded by py-qgis-server
                    package._is_py_qgis_server = True  # type: ignore [attr-defined]

                    # Initialize the plugin
                    match plugin_type:
                        case PluginType.SERVER:
                            init = package.serverClassFactory(interface)
                        case PluginType.PROCESSING:
                            init = processes.init_processing(package)
                        case _ as unreachable:
                            assert_never(unreachable)

                    self._plugins[plugin] = Plugin(
                        name=name,
                        path=Path(package.__file__).parent,   # type: ignore
                        plugin_type=plugin_type,
                        init=init,
                    )
                    logger.info(f"Loaded plugin {plugin}")
                except Exception:
                    raise PluginError(
                        f"Error loading plugin '{plugin}':\n{traceback.format_exc()}",
                    ) from None

    @property
    def providers(self) -> Iterator['qgis.core.QgsProcessingProvider']:
        """ Return published providers
        """
        from qgis.core import QgsApplication
        reg = QgsApplication.processingRegistry()
        return (reg.providerById(_id) for _id in self._providers)


def find_plugins(
    path: Path | str,
    plugin_type: PluginType,
) -> Iterator[Tuple[str, configparser.ConfigParser]]:
    """ return list of plugins in given path
    """
    path = Path(path)
    for plugin in path.glob("*"):

        if not plugin.is_dir():
            # Warn about dangling symlink
            # This occurs when running in docker container
            # and symlink target path are not visible from the
            # container - give some hint for debugging
            if plugin.is_symlink():
                logger.warning(
                    f"*** The symbolic link '{plugin}' is not resolved."
                    " If you are running in docker container please consider"
                    "mounting the target path in the container.",
                )
            continue

        logger.debug(f"Looking for plugin in '{plugin}'")

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

        yield plugin.name, cp


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


def install_plugins(conf: QgisPluginConfig):
    """ Install required plugins from installation
    """
    plugins = conf.install
    if not plugins:
        # Nothing to install
        print("No plugins to install", file=sys.stderr)  # noqa T201
        return

    import subprocess  # nosec

    assert_precondition(conf.plugin_manager.is_absolute())

    logger.info("Installing plugins")

    install_path = conf.paths[0]
    install_path.mkdir(mode=0o775, parents=True, exist_ok=True)

    def _run(*args):
        res = subprocess.run(
            [conf.plugin_manager, *args],  # nosec; path is checked to be absolute
            cwd=str(install_path),
        )
        if res.returncode > 0:
            raise RuntimeError(f"'qgis-plugin-manager' failed with return code {res}")

    if not (install_path / 'sources.list').exists():
        _run("init")

    try:
        _run("update")
    except RuntimeError:
        logger.error("Cannot update plugins index, cancelling installation...")
        return

    for plugin in plugins:
        _run("install", plugin)
