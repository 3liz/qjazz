
from typing import List, Optional, Self

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDateTimeRange,
    QgsProject,
    QgsRectangle,
)
from qgis.server import QgsServerProjectUtils as Pu

from ..core import extent
from .crs import CrsRef, QgsCrs3D
from .metadata import DateTime


def transform_extent(
    p: QgsProject,
    dest: QgsCoordinateReferenceSystem,
    r: QgsRectangle,
) -> QgsRectangle:

    transform = QgsCoordinateTransform(QgsCrs3D(p), dest, p)
    transform.setBallparkTransformsAreAppropriate(True)
    return transform.transformBoundingBox(r)


def parse_bbox(r: QgsRectangle) -> List[float]:
    return [
        r.xMinimum(),
        r.xMaximum(),
        r.yMinimum(),
        r.yMaximum(),
    ]


def compute_extent_from_layers(p: QgsProject) -> QgsRectangle:
    """  Combine extent from layers
    """
    restricted_layers = Pu.wmsRestrictedLayers(p)
    extent = QgsRectangle()
    for layer in p.mapLayers().values():
        if layer.name() in restricted_layers:
            continue

        layer_extent = layer.extent()
        if layer_extent.isEmpty():
            continue

        transform = QgsCoordinateTransform(layer.crs(), p.crs(), p)
        transform.setBallparkTransformsAreAppropriate(True)
        layer_extent = transform.transformBoundingBox(layer.extent())

        extent.combineExtentWith(layer_extent)

    return extent


class SpatialExtent(extent.SpatialExtent):

    @classmethod
    def from_project(
        cls,
        p: QgsProject,
        default_crs: QgsCoordinateReferenceSystem,
    ) -> Optional[Self]:
        """ Build the spatial extent

            bbox_crs is the crs of the bbox property if this one is
            different from the storage crs.
        """
        # wmsExtent
        # XXX Check what is the CRS of the wmsExtent
        # We assume that extent is in StorageCrs
        extent = Pu.wmsExtent(p)
        if extent.isEmpty():
            # Compute extent from layers
            extent = compute_extent_from_layers(p)

        if extent.isEmpty():
            return None

        bbox = parse_bbox(transform_extent(p, default_crs, extent))
        storage_crs_bbox = parse_bbox(extent)

        if Qgis.QGIS_VERSION_INT >= 33800:
            elev = p.elevationProperties()
            if elev:
                elev_range = elev.elevationRange()
                if not elev_range.isInfinite():
                    bbox.extend((elev_range.lower(), elev_range.upper()))

        return cls(
            bbox=[bbox],
            crs=CrsRef.from_qgis(default_crs),
            storage_crs_bbox=[storage_crs_bbox],
        )


class TemporalExtent(extent.TemporalExtent):

    @classmethod
    def from_range(cls, tr: QgsDateTimeRange) -> Optional[Self]:
        if not tr.isEmpty():
            return cls(
                interval=[[
                    DateTime(tr.begin()),
                    DateTime(tr.end()),
                ]],
            )
        else:
            return None

    @classmethod
    def from_project(cls, p: QgsProject) -> Optional[Self]:
        ts = p.timeSettings()
        if ts:
            return cls.from_range(ts.temporalRange())
        else:
            return None


class Extent(extent.Extent):

    @classmethod
    def from_project(cls, p: QgsProject, default_crs: QgsCoordinateReferenceSystem) -> Self:
        return cls(
            spatial=SpatialExtent.from_project(p, default_crs),
            temporal=TemporalExtent.from_project(p),
        )
