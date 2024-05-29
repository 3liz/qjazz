#
#
#
from pathlib import Path

from typing_extensions import Optional

from qgis.core import (
    Qgis,
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
        self._job_id = "00000000-0000-0000-0000-000000000000"
        self._store_url: str = f"./jobs/{self._job_id}/files"
        self._advertised_services_url = "."
        # Initialize temporaryFolder with workdir
        self._workdir = self._config.workdir.joinpath(self._job_id)
        self.setTemporaryFolder(str(self._workdir))

    @property
    def job_id(self) -> str:
        return self._job_id

    @job_id.setter
    def job_id(self, ident: str):
        self._job_id = ident
        self._workdir = self._config.workdir.joinpath(ident)

    @property
    def advertised_ows_services_url(self) -> str:
        return self._advertised_services_url

    @advertised_ows_services_url.setter
    def advertised_ows_services_url(self, url: str):
        self._advertised_services_url = url

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
        return self._workdir

    @property
    def destination_project(self) -> Optional[QgsProject]:
        return self._destination_project

    @destination_project.setter
    def destination_project(self, project: Optional[QgsProject]):
        self._destination_project = project

    def create_project(self, name: str) -> QgsProject:
        """ Create a destination project

            Note: this do NOT set the context destination_project.
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

        destination_project.setFileName(f"{self.workdir.joinpath(name)}.qgs")

        # Store files as relative path
        destination_project.setFilePathStorage(Qgis.FilePathType.Relative)

        # Write advertised URLs
        destination_project.writeEntry('WMSUrl', '/', self.ows_reference(name, "WMS"))
        destination_project.writeEntry('WCSUrl', '/', self.ows_reference(name, "WCS"))
        destination_project.writeEntry('WFSUrl', '/', self.ows_reference(name, "WFS"))
        destination_project.writeEntry('WMTSUrl', '/', self.ows_reference(name, "WMTS"))

        return destination_project

    def store_reference_url(self, resource: str) -> str:
        """ Return a proper reference url for the resource
        """
        return f"{self._store_url}/{resource}"

    def file_reference(self, path: Path) -> str:
        return self.store_reference_url(str(path.relative_to(self.workdir)))

    def ows_reference(
        self, name: str,
        service: Optional[str],
        request: Optional[str] = None,
        query: Optional[str] = None,
    ) -> str:
        service = service or "WMS"
        request = request or "GetCapabilities"
        url = (
            f"{self.advertised_ows_services_url}/{self.job_id}/{name}"
            f"?SERVICE={service}&REQUEST={request}"
        )
        if query:
            url = f"{url}&{query}"

        return url
