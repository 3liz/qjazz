#
# Handle processing plugins
#
import sys
import traceback

from pathlib import Path
from types import ModuleType

from pydantic import BaseModel
from typing_extensions import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Sequence,
    Set,
)

if sys.version_info < (3, 11):
    import tomli as toml  # type: ignore
else:
    import tomllib as toml

from qgis.core import QgsApplication, QgsProcessingProvider

from .. import logger

BuiltinProviderSet = Set[Literal['grass', 'otb']]


class ProcessesConfig(BaseModel):
    # List of unexposed providers
    discard: List[str] = []
    styles: Optional[Dict[str, Dict[str, Path]]] = None


class ProcessesLoader:
    def __init__(self, providers: List[str], allow_scripts: bool = True):

        self._discard: set[str] = set()
        self._providers = providers
        self._register = False

        reg = QgsApplication.processingRegistry()
        reg.providerAdded.connect(self._registerProvider)

        # Support models and script
        for ident in (('model', 'script') if allow_scripts else ('model',)):
            if reg.providerById(ident):
                self._providers.append(ident)

    def load_builtin_providers(self, extras: BuiltinProviderSet) -> Sequence[QgsProcessingProvider]:
        #
        # Load builtins providers
        # From /usr/share/qgis/python/plugins/processing/core/Processing.py
        #
        self._register = False
        reg = QgsApplication.processingRegistry()

        def _load_builtin(n: str) -> Optional[QgsProcessingProvider]:
            p = None
            try:
                match n:
                    case 'grass':
                        logger.info("Registering builtin GRASS provider")
                        from grassprovider.Grass7AlgorithmProvider import Grass7AlgorithmProvider
                        p = Grass7AlgorithmProvider()
                        reg.addProvider(p)
                    case 'otb':
                        logger.info("Registering builtin OTB provider")
                        from otbprovider.OtbAlgorithmProvider import OtbAlgorithmProvider
                        p = OtbAlgorithmProvider()
                        reg.addProvider(p)
            except Exception:
                logger.error(traceback.format_exc())

            return p

        return tuple(filter(None, (_load_builtin(n) for n in extras)))

    def __del__(self):
        # Ensure proper disconnection from QT slot
        reg = QgsApplication.processingRegistry()
        reg.providerAdded.disconnect(self._registerProvider)

    def _registerProvider(self, id_: str):
        """ Called when a provider is added
            to the registry
        """
        if self._register and id_ not in self._discard:
            logger.info("* Registering processing provider: %s", id_)
            self._providers.append(id_)

    def read_configuration(self, path: Path):
        """ Read processes configuration as toml file
        """
        path = path.joinpath('processes.toml')
        if not path.exists():
            return

        logger.info("Reading processes configuration file in %s", path)

        with path.open() as fp:
            conf = ProcessesConfig.model_validate(toml.loads(fp.read()))
            self._discard.union(conf.discard)

        if conf.styles:
            from processing.core.Processing import RenderingStyles

            # Load styles for processing output
            styles: Dict[str, Dict[str, str]] = {}
            for alg, keys in conf.styles.items():
                styles.setdefault(alg, {})
                for key, qmlpath in keys.items():
                    qml = path.parent.joinpath(qmlpath)
                if qml.exists():
                    styles[alg][key] = str(qml)
                else:
                    logger.warning("Style file not found:  %s", qml)
            RenderingStyles.styles.update(styles)

    def init_processing(self, package: ModuleType) -> Any:  # noqa ANN401 
        """ Initialize processing plugin
        """
        self._register = True
        try:
            # module __file__ may be None
            if package.__file__ is not None:
                path = Path(package.__file__).parent
                self.read_configuration(path)
            init = package.classFactory(None)
            init.initProcessing()
        finally:
            self._register = False
        return init
