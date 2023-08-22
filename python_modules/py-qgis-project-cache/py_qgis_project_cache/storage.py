#
# Copyright 2023 3liz
# all rights reserved
""" Handle Qgis storage metadata
"""
from datetime import datetime
from pathlib import Path

from urllib.parse import urlunsplit
from typing import Generator, Optional, Union

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsProjectStorage,
    QgsProject,
    QgsProjectBadLayerHandler,
)
from qgis.server import QgsServerProjectUtils

from py_qgis_contrib.core import logger

from .config import ProjectsConfig
from .common import Url, ProjectMetadata


class StrictCheckingFailure(Exception):
    pass


def file_metadata(path: Path):
    st = path.stat()
    return ProjectMetadata(
        uri=str(path),
        name=path.stem,
        scheme='file',
        storage='file',
        last_modified=st.st_mtime
    )


def project_storage_metadata(uri: str, storage: Union[str | QgsProjectStorage]) -> QgsProjectStorage.Metadata:
    """ Read metadata about project
    """
    if isinstance(storage, str):
        storage = QgsApplication.projectStorageRegistry().projectStorageFromType(storage)

    res, md = storage.readProjectStorageMetadata(uri)
    if not res:
        logger.error("Failed to read storage metadata for %s", uri)
        raise FileNotFoundError(uri)
    return md


def storage_from_uri(uri: str) -> Optional[QgsProjectStorage]:
    return QgsApplication.projectStorageRegistry().projectStorageFromUri(uri)


def list_storage_projects(url: Url, storage: Union[str | QgsProjectStorage]) -> Generator[ProjectMetadata, None, None]:
    """ Scan project files from path

        If path contains an uri scheme then use QgsProjectStorage to list files
        (see https://api.qgis.org/api/classQgsProjectStorage.html)

        Otherwise assume we are dealing with files
    """
    if isinstance(storage, str):
        storage = QgsApplication.projectStorageRegistry().projectStorageFromType(storage)

    uri = urlunsplit(url)
    assert storage.isSupportedUri(uri), f"Invalide uri for storage '{storage.type()}': {uri}"

    for uri in storage.listProjects(uri):
        md = project_storage_metadata(uri, storage)
        last_modified = md.lastModified.toPyDateTime()
        yield ProjectMetadata(
            uri=md.uri,
            name=md.name,
            scheme=url.scheme,
            storage=storage.type(),
            last_modified=datetime.timestamp(last_modified),
        )


def remove_advertised_urls(self, project: QgsProject) -> None:
    """ Remove advertised url's since they
        may interfere with proxy_urls
    """
    # Disable ows urls defined in project
    # May be needed because it overrides
    # any proxy settings
    project.writeEntry("WMSUrl", "/", "")
    project.writeEntry("WFSUrl", "/", "")
    project.writeEntry("WCSUrl", "/", "")
    project.writeEntry("WMTSUrl", "/", "")


def load_project_from_uri(uri: str, config: ProjectsConfig) -> QgsProject:
    """ Read project from uri

        May be used by protocol-handlers to instanciate project
        from uri.
    """
    logger.debug("Reading Qgis project '%s'", uri)

    version_int = Qgis.QGIS_VERSION_INT

    # see https://github.com/qgis/QGIS/pull/49266
    if version_int < 32601:
        project = QgsProject()
        readflags = QgsProject.ReadFlags()
        if config.trust_layer_metadata:
            readflags |= QgsProject.FlagTrustLayerMetadata
        if config.disable_getprint:
            readflags |= QgsProject.FlagDontLoadLayouts
    else:
        project = QgsProject(capabilities=Qgis.ProjectCapabilities())
        readflags = Qgis.ProjectReadFlags()
        if config.trust_layer_metadata:
            readflags |= Qgis.ProjectReadFlag.TrustLayerMetadata
        if config.disable_getprint:
            readflags |= Qgis.ProjectReadFlag.DontLoadLayouts

    if version_int >= 32800 and config.force_readonly_layers:
        readflags |= Qgis.ProjectReadFlag.ForceReadOnlyLayers

    # Handle bad layers
    badlayerh = BadLayerHandler()
    project.setBadLayerHandler(badlayerh)
    if not project.read(uri, readflags):
        raise RuntimeError(f"Failed to read Qgis project {uri}")

    if config.strict_check and not badlayerh.validateLayers(project):
        raise StrictCheckingFailure

    if config.disable_advertised_urls:
        remove_advertised_urls(project)

    return project


class BadLayerHandler(QgsProjectBadLayerHandler):

    def __init__(self):
        super().__init__()
        self.badLayerNames = set()

    def handleBadLayers(self, layers) -> None:
        """ See https://qgis.org/pyqgis/3.0/core/Project/QgsProjectBadLayerHandler.html
        """
        super().handleBadLayers(layers)

        nameElements = (lyr.firstChildElement("layername") for lyr in layers if lyr)
        self.badLayerNames = {elem.text() for elem in nameElements if elem}

    def validateLayers(self, project: QgsProject) -> bool:
        """ Check layers

            If layers are excluded do not count them as bad layers
            see https://github.com/qgis/QGIS/pull/33668
        """
        if self.badLayerNames:
            logger.error("Found bad layers: %s", self.badLayerNames)
            restricteds = set(QgsServerProjectUtils.wmsRestrictedLayers(project))
            return self.badLayerNames.issubset(restricteds)
        return True
