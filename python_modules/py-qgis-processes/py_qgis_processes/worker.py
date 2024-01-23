import asyncio
import multiprocessing as mp

from dataclasses import dataclasse

from py_qgis_cache import CacheManager, CheckoutStatus
from py_qgis_contrib.core.qgis import (
    PluginType,
    QgisPluginService,
    init_processing,
    show_qgis_settings,
)

from .config import WorkerConfig


class WorkerError(Exception):
    def __init__(self, code: int, details: Any = None):
        self.code = code
        self.details = details


class Worker(mp.Process):
    """ Processing worker
    """
    def __init__(self, conf: WorkerConfig, name: Optional[str] = None):
        super().__init__(name=name or config.name, daemon=True)
        self._conf = config
        self._parent_io, self._child_io = mp.Pipe(duplex=True)
        self._timeout = config.process_timeout
        self._num_runs = 0

    @property
    def config(self) -> WorkerConfig:
        return self._conf

    def run(self):
        """ Override """
        # Initialize Qgis processing
        setup_processing(self._conf)

        # Wait for inputs
        msg = self._child_io.recv()

        # process

        # reply
        self._child_io.send(resp)

        # Exit if max number of runs is reached
        self._num_runs += 1
        if self._num_runs >= self._conf.max_runs_per_worker:
            return


def setup_processing(conf: WorkerConfig):
    """  Initialize qgis application and qgis processing
    """
    # Enable qgis server debug verbosity
    if logger.isEnabledFor(logger.LogLevel.DEBUG):
        os.environ['QGIS_SERVER_LOG_LEVEL'] = '0'
        os.environ['QGIS_DEBUG'] = '1'

    # Global processing settings
    settings = {
        "Processing/Configuration/PREFER_FILENAME_AS_LAYER_NAME": "false",  # Qgis < 3.30
        "qgis/configuration/prefer-filename-as-layer-name": "false"         # Qgis >= 3.30
    }

    # Set folders for scripts and models search

    def _folders_settings(setting, subfolder):
        folders = ';'.join(str(p / subfolder) for p in conf.plugins.paths if (p / subfolder).is_dir())
        if folders:
            settings[setting] = folders

    # Set up scripts and model folder settings
    # XXX  Note that if scripts folder is not set then ScriptAlgorithmProvider will crash !
    _folder_settings("Processing/Configuration/SCRIPTS_FOLDERS", "scripts")
    _folder_settings("Processing/Configuration/MODELS_FOLDER", "models")

    qgis.init_qgis_application()
    qgis.init_qgis_processing()

    if logger.isEnabledFor(logger.LogLevel.TRACE):
        print(show_qgis_settings())  # noqa T201

    # Initialize cache manager
    CacheManager.initialize_handlers()
    cm = CacheManager(config.projects)
    cm.register_as_service()

    # Load plugins
    plugin_s = QgisPluginService(config.plugins)
    plugin_s.load_plugins(PluginType.SERVER, server_iface)
    plugin_s.register_as_service()

    
