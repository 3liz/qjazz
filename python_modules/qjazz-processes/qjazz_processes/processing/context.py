#
#
#

from pathlib import Path
from string import Template

from typing_extensions import Optional, cast

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsProcessingContext,
    QgsProject,
)

from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import assert_precondition

from .config import ProcessingConfig
from .utils import get_valid_filename


class ProcessingContext(QgsProcessingContext):

    def __init__(self, config: Optional[ProcessingConfig] = None):
        super().__init__()
        self._destination_project: Optional[QgsProject] = None
        self._config = config or ProcessingConfig(workdir=Path())

        self.public_url = ""
        self.files: set[str] = set()

        self.job_id = "00000000-0000-0000-0000-000000000000"
        self.store_url(self._config.store_url)
        self.advertised_services_url(self._config.advertised_services_url)

    @property
    def job_id(self) -> str:
        return self._job_id

    @job_id.setter
    def job_id(self, ident: str):
        self._job_id = ident
        self._workdir = self._config.workdir.joinpath(ident)
        # Initialize temporaryFolder with workdir
        self.setTemporaryFolder(str(self._workdir))

    def advertised_services_url(self, url: Template):
        """ Set advertised_services_url template
        """
        self._advertised_services_url = url

    def store_url(self, url: Template):
        """ Set store_url template
        """
        self._store_url = url

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

        # Set project filename
        filename = get_valid_filename(name)
        destination_project.setFileName(f"{self.workdir.joinpath(filename)}.qgz")

        # Store files as relative path
        destination_project.setFilePathStorage(Qgis.FilePathType.Relative)

        # Write advertised URLs
        destination_project.writeEntry('WMSUrl', '/', self._ows_reference(filename, "WMS"))
        destination_project.writeEntry('WCSUrl', '/', self._ows_reference(filename, "WCS"))
        destination_project.writeEntry('WFSUrl', '/', self._ows_reference(filename, "WFS"))
        destination_project.writeEntry('WMTSUrl', '/', self._ows_reference(filename, "WMTS"))

        return destination_project

    def store_reference_url(self, resource: str) -> str:
        """ Return a proper reference url for the resource
        """
        return self._store_url.substitute(
            resource=resource,
            jobId=self.job_id,
            public_url=self.public_url,
        )

    def file_reference(self, path: Path, append_to_files: bool = True) -> str:
        basename = str(path.relative_to(self.workdir))
        if append_to_files:
            self.files.add(basename)
        return self.store_reference_url(basename)

    def _ows_reference(
        self,
        name: str,
        service: Optional[str],
        *,
        version: Optional[str] = None,
        request: Optional[str] = None,
        query: Optional[str] = None,
    ) -> str:
        service = service or "WMS"
        request = request or "GetCapabilities"
        advertised_services_url = self._advertised_services_url.substitute(
            name=name,
            jobId=self.job_id,
            public_url=self.public_url,
        )
        url = f"{advertised_services_url}?SERVICE={service}&REQUEST={request}"
        if version:
            url = f"{url}&VERSION={version}"
        if query:
            url = f"{url}&{query}"

        return url

    def ows_reference(
        self,
        *,
        service: Optional[str],
        request: Optional[str] = None,
        version: Optional[str] = None,
        query: Optional[str] = None,
    ) -> str:
        assert_precondition(self._destination_project is not None, "Destination project required")
        return self._ows_reference(
            Path(cast(QgsProject, self._destination_project).fileName()).stem,
            service,
            version=version,
            request=request,
            query=query,
        )
