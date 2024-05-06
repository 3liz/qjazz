#
#
#
from pathlib import Path

from typing_extensions import Optional

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingContext,
    QgsProject,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import confservice

from .config import ProcessingConfig


class ProcessingContext(QgsProcessingContext):

    def __init__(self, config: Optional[ProcessingConfig] = None):
        super().__init__()
        self._base_url: Optional[str] = None
        self._destination_project: Optional[QgsProject] = None
        self._config = config or confservice.conf.processing

    @property
    def url(self) -> Optional[str]:
        return self._base_url

    @url.setter
    def url(self, url: Optional[str]):
        self._base_url = url

    @property
    def config(self) -> ProcessingConfig:
        return self._config

    @config.setter
    def config(self, config: ProcessingConfig):
        self._config = config

    @property
    def workdir(self) -> Path:
        return Path(self.temporaryFolder())

    @workdir.setter
    def workdir(self, path: Path):
        self.setTemporaryFolder(str(path))

    @property
    def destination_project(self) -> Optional[QgsProject]:
        return self._destination_project

    @destination_project.setter
    def destination_project(self, project: Optional[QgsProject]):
        self._destination_project = project

    def create_project(self) -> QgsProject:
        """ Create destination project
        """
        project = self.project()
        if project:
            crs = project.crs()
        else:
            crs = QgsCoordinateReferenceSystem()
            crs.createFromUserInput(self.config.default_crs)
            if not crs.isValid():
                logger.error("Invalid default crs %s", self.config.default_crs)

        destination_project = QgsProject()
        if crs.isValid():
            destination_project.setCrs(crs, self.config.adjust_ellipsoid)

        return destination_project
