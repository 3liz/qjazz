#
# Copyright 2023 3liz
# all rights reserved
""" Handle Qgis storage metadata
"""
from typing import Protocol

from qgis.core import Qgis, QgsProject, QgsProjectBadLayerHandler
from qgis.server import QgsServerProjectUtils

from qjazz_contrib.core import logger

from .errors import StrictCheckingFailure, UnreadableResource


class ProjectLoaderConfig(Protocol):
    @property
    def trust_layer_metadata(self) -> bool: ...
    @property
    def disable_getprint(self) -> bool: ...
    @property
    def force_readonly_layers(self) -> bool: ...
    @property
    def dont_resolve_layers(self) -> bool: ...
    @property
    def disable_advertised_urls(self) -> bool: ...
    @property
    def ignore_bad_layers(self) -> bool: ...


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


def load_project_from_uri(uri: str, config: ProjectLoaderConfig) -> QgsProject:
    """ Read project from uri

        May be used by protocol-handlers to instanciate project
        from uri.
    """
    logger.debug("Reading Qgis project '%s'", uri)

    # see https://github.com/qgis/QGIS/pull/49266
    project = QgsProject(capabilities=Qgis.ProjectCapabilities())

    readflags = Qgis.ProjectReadFlags()
    if config.dont_resolve_layers:
        # Activate all optimisation flags
        readflags |= Qgis.ProjectReadFlag.TrustLayerMetadata
        readflags |= Qgis.ProjectReadFlag.DontLoadLayouts
        readflags |= Qgis.ProjectReadFlag.ForceReadOnlyLayers
        readflags |= Qgis.ProjectReadFlag.DontResolveLayers
    else:
        if config.trust_layer_metadata:
            readflags |= Qgis.ProjectReadFlag.TrustLayerMetadata
        if config.disable_getprint:
            readflags |= Qgis.ProjectReadFlag.DontLoadLayouts
        if config.force_readonly_layers:
            readflags |= Qgis.ProjectReadFlag.ForceReadOnlyLayers

    # Handle bad layers
    if not config.dont_resolve_layers:
        badlayerh = BadLayerHandler()
        project.setBadLayerHandler(badlayerh)
    else:
        logger.debug("Disabled layer's resolution for '%s'", uri)
        badlayerh = None

    if not project.read(uri, readflags):
        raise UnreadableResource(uri)

    if badlayerh and not config.ignore_bad_layers:
        if not badlayerh.validateLayers(project):
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
