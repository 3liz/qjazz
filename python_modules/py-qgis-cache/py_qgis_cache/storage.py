#
# Copyright 2023 3liz
# all rights reserved
""" Handle Qgis storage metadata
"""
from qgis.core import Qgis, QgsProject, QgsProjectBadLayerHandler
from qgis.server import QgsServerProjectUtils

from py_qgis_contrib.core import logger

from .config import ProjectsConfig


class StrictCheckingFailure(Exception):
    pass


class UnreadableResource(Exception):
    """ Indicates that the  ressource exists but is not readable
    """
    pass


def remove_advertised_urls(project: QgsProject) -> None:
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

    #version_int = Qgis.QGIS_VERSION_INT

    # see https://github.com/qgis/QGIS/pull/49266
    project = QgsProject(capabilities=Qgis.ProjectCapabilities())
    readflags = Qgis.ProjectReadFlags()
    if config.trust_layer_metadata:
        readflags |= Qgis.ProjectReadFlag.TrustLayerMetadata
    if config.disable_getprint:
        readflags |= Qgis.ProjectReadFlag.DontLoadLayouts
    if config.force_readonly_layers:
        readflags |= Qgis.ProjectReadFlag.ForceReadOnlyLayers
    if config.dont_resolve_layers:
        readflags |= Qgis.ProjectReadFlag.DontResolveLayers

    # Handle bad layers
    if config.strict_check:
        badlayerh = BadLayerHandler()
        project.setBadLayerHandler(badlayerh)
    else:
        badlayerh = None

    if not project.read(uri, readflags):
        raise UnreadableResource(uri)

    if badlayerh and not badlayerh.validateLayers(project):
        raise StrictCheckingFailure(uri)

    if config.disable_advertised_urls:
        remove_advertised_urls(project)

    return project


class BadLayerHandler(QgsProjectBadLayerHandler):

    def __init__(self):
        super().__init__()
        self.badLayerNames = set()

    def handleBadLayers(self, layers):
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
