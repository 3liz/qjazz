#
# Handle processing plugins
#

from pathlib import Path
from typing import List

from pydantic import BaseModel
from typing_extensions import Any, Dict, Optional

try:
    # 3.11+
    import toml
except ModuleNotFoundError:
    import tomli as toml

from qgis.core import QgsApplication

from .. import logger


class ProcessesConfig(BaseModel):
    # List of unexposed providers
    discard: List[str] = []
    styles: Optional[Dict[str, Dict[str, Path]]] = None


class ProcessesLoader:
    def __init__(self, providers):

        self._discard = set()
        self._providers = providers
        self._register = False

        reg = QgsApplication.processingRegistry()
        reg.providerAdded.connect(self._registerProvider)

    def __del__(self):
        # Ensure proper disconnection from QT slot
        reg = QgsApplication.processingRegistry()
        reg.providerAdded.disconnect(self._registerProvider)

    def _registerProvider(self, _id: str):
        """ Called when a provider is added
            to the registry
        """
        if self._register and _id not in self._discard:
            logger.info("Registering processing provider: %s", _id)
            self._providers.append(_id)

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
            styles = {}
            for alg, keys in conf.styles.items():
                styles.setdefault(alg, {})
                for key, qmlpath in keys.items():
                    qml = path.parent.joinpath(qmlpath)
                if qml.exists():
                    styles[alg][key] = str(qml)
                else:
                    logger.warning("Style file not found:  %s", qml)
            RenderingStyles.styles.update(styles)

    def init_processing(self, package) -> Any:
        """ Initialize processing plugin
        """
        self._register = True
        try:
            path = Path(package.__file__).parent
            self.read_configuration(path)
            init = package.classFactory(None)
            init.initProcessing()
        finally:
            self._register = False
        return init
