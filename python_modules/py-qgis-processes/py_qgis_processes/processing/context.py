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
        self._destination_project: Optional[QgsProject] = None
        self._config = config or confservice.conf.processing
        self._store_url: str = "./jobs/00000000-0000-0000-0000-000000000000/files"

    @property
    def store_url(self) -> str:
        return self._store_url

    @store_url.setter
    def store_url(self, url: str):
        self._store_url = url.removesuffix('/')

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

    def reference_url(self, resource: str) -> str:
        """ Return a proper reference url for the resource
        """
        return f"{self._store_url}/{resource}"

    def file_reference(self, path: Path) -> str:
        return self.reference_url(str(path.relative_to(self.workdir)))
