from functools import cached_property
from typing import (
    Iterator,
    Optional,
)

from qgis.core import (
    Qgis,
    QgsMapLayer,
    QgsProject,
)
from qgis.server import QgsServerProjectUtils


class LayerAccessor:
    def __init__(self, project: QgsProject):
        self._project = project

    @property
    def project(self) -> QgsProject:
        return self._project

    @cached_property
    def use_layer_ids(self) -> bool:
        return QgsServerProjectUtils.wmsUseLayerIds(self._project)

    @cached_property
    def restricted_layers(self) -> set[str]:
        return set(QgsServerProjectUtils.wmsRestrictedLayers(self._project))

    def layer_by_name(self, name: str) -> Optional[QgsMapLayer]:
        """Return layer by name according to WMS preferences"""
        # NOTE: mapLayersByShortName check for shortname and for name
        # if short name is not available
        if self.use_layer_ids:
            return self._project.mapLayer(name)
        layer = self._project.mapLayersByShortName(name)
        if layer:
            return layer[0]
        return None

    def layers(self) -> Iterator[QgsMapLayer]:
        # root = project.layerTreeRoot()
        restricted_layers = self.restricted_layers
        for layer in self._project.mapLayers().values():
            if layer.name() not in restricted_layers:
                yield layer

    def layer_name(self, layer: QgsMapLayer) -> str:
        """Get the layer name according if the shortname is set"""
        if self.use_layer_ids:
            return layer.id()
        if Qgis.QGIS_VERSION_INT < 33800:
            name = layer.shortName()
        else:
            name = layer.serverProperties().shortName()

        return name if name else layer.name()
