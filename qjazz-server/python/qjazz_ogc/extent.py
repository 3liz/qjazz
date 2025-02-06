from typing import Iterator, List, Optional, Self, assert_never

from qgis.core import (
    Qgis,
    QgsBox3D,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDataProvider,
    QgsDateTimeRange,
    QgsMapLayer,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.server import QgsServerProjectUtils as Pu

from .core import extent
from .crs import CrsRef, QgsCrs3D
from .metadata import DateTime


# Bbox format is [xmin, ymin [,zmin], xmax, ymax [,zmax]]
def parse_bbox(r: QgsRectangle, invert_axis: bool = False) -> List[float]:
    if invert_axis:
        return [
            r.yMinimum(),
            r.xMinimum(),
            r.yMaximum(),
            r.xMaximum(),
        ]
    else:
        return [
            r.xMinimum(),
            r.yMinimum(),
            r.xMaximum(),
            r.yMaximum(),
        ]


# Bbox format is [xmin, ymin [,zmin], xmax, ymax [,zmax]]
def parse_bbox3d(r: QgsBox3D, invert_axis: bool = False) -> List[float]:
    if invert_axis:
        return [
            r.xMinimum(),
            r.yMinimum(),
            r.zMinimum(),
            r.xMaximum(),
            r.yMaximum(),
            r.zMaximum(),
        ]
    else:
        return [
            r.yMinimum(),
            r.xMinimum(),
            r.zMinimum(),
            r.yMaximum(),
            r.xMaximum(),
            r.zMaximum(),
        ]


def parse_extent(extent: QgsRectangle | QgsBox3D, invert_axis: bool = False) -> List[float]:
    match extent:
        case QgsRectangle():
            return parse_bbox(extent, invert_axis)
        case QgsBox3D():
            return parse_bbox3d(extent, invert_axis) if extent.is3D() else parse_bbox(
                extent.toRectangle(),
                invert_axis,
            )
        case _ as unreachable:
            assert_never(unreachable)


def extend_bbox_3d(r: List[float], zmin: float, zmax: float):
    r.insert(2, zmin)
    r.append(zmax)


def transform_extent(
    r: QgsRectangle,
    from_crs: QgsCoordinateReferenceSystem,
    dest_crs: QgsCoordinateReferenceSystem,
    p: QgsProject,
) -> QgsRectangle:
    transform = QgsCoordinateTransform(from_crs, dest_crs, p)
    transform.setBallparkTransformsAreAppropriate(True)
    return transform.transformBoundingBox(r)


def compute_extent_from_layers(
    p: QgsProject,
    dest_crs: Optional[QgsCoordinateTransform] = None,
) -> QgsRectangle:
    """  Combine extent from layers
    """
    restricted_layers = Pu.wmsRestrictedLayers(p)
    extent = QgsRectangle()

    if not dest_crs:
        dest_crs = p.crs()

    for layer in p.mapLayers().values():
        if layer.name() in restricted_layers:
            continue

        layer_extent = layer.extent()
        if layer_extent.isEmpty():
            continue

        layer_extent = transform_extent(layer_extent, layer.crs(), dest_crs, p)
        extent.combineExtentWith(layer_extent)

    return extent


def layer_extents_from_metadata(
    provider: QgsDataProvider,
    storage_crs: QgsCoordinateReferenceSystem,
    project: QgsProject,
) -> Iterator[QgsBox3D]:

    # Trust metadata
    md = provider.layerMetadata()
    for xt in md.extent().spatialExtents():
        box = xt.bounds
        r = box.toRectangle()
        if r.isEmpty():
            continue
        xt_crs = xt.extentCrs
        if xt_crs.isValid():
            r = transform_extent(r, xt_crs, storage_crs, project)
            box = QgsBox3D(r, box.zMinimum(), box.zMaximum())
        else:
            yield box


class SpatialExtent(extent.SpatialExtent):

    @classmethod
    def from_project(
        cls,
        p: QgsProject,
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

        default_crs = CrsRef.default()
        default_crs_qgis = default_crs.to_qgis()
        storage_crs_qgis = p.crs()

        bbox = parse_extent(
            transform_extent(extent, QgsCrs3D(p), default_crs_qgis, p),
            default_crs_qgis.hasAxisInverted(),
        )
        storage_crs_bbox = parse_extent(extent, storage_crs_qgis.hasAxisInverted())

        if Qgis.QGIS_VERSION_INT >= 33800:
            elev = p.elevationProperties()
            if elev:
                elev_range = elev.elevationRange()
                if not elev_range.isInfinite():
                    zmin, zmax = elev_range.lower(), elev_range.upper()
                    extend_bbox_3d(bbox, zmin, zmax)
                    extend_bbox_3d(storage_crs_bbox, zmin, zmax)

        return cls(
            bbox=[bbox],
            crs=default_crs,
            storage_crs_bbox=[storage_crs_bbox],
        )

    @classmethod
    def from_layer(
        cls,
        layer: QgsMapLayer,
    ) -> Optional[Self]:
        """ Build the spatial extent

            bbox_crs is the crs of the bbox property if this one is
            different from the storage crs.
        """
        provider = layer.dataProvider()
        if not provider:
            return None

        storage_crs = provider.crs()

        default_crs = CrsRef.default()

        p = layer.project()

        storage_extents = list(layer_extents_from_metadata(provider, storage_crs, p))
        if not storage_extents:
            # Try to calculate directly from the provider
            if Qgis.QGIS_VERSION_INT < 33800:
                extent = layer.extent()
            else:
                # XXX Do not use `QgsDataProvider::extent3D: QGIS crash (segfault)
                # when asking for extent3D with some providers
                extent = layer.extent3D()
                if not extent.is3D():
                    # XXX: fallback to 2D extent since extend3D() may be inconsistant
                    # in regard to the 2D extent
                    extent = layer.extent()

            if not extent.isEmpty():
                storage_extents = [extent]

        if not storage_extents:
            return None

        default_crs_qgis = default_crs.to_qgis()

        # Get bbox extents in default crs
        def bbox_extents() -> Iterator[QgsBox3D]:
            for box in storage_extents:
                match box:
                    case QgsBox3D():
                        r = transform_extent(box.toRectangle(), storage_crs, default_crs_qgis, p)
                        if box.is3D():
                            yield QgsBox3D(r, box.zMinimum(), box.zMaximum())
                        else:
                            yield r
                    case _:
                        yield transform_extent(box, storage_crs, default_crs_qgis, p)

        return cls(
            bbox=[parse_extent(
                b,
                default_crs_qgis.hasAxisInverted(),
            ) for b in bbox_extents()],
            crs=default_crs,
            storage_crs_bbox=[parse_extent(
                b,
                storage_crs.hasAxisInverted(),
            ) for b in storage_extents],
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

    @classmethod
    def from_layer(cls, layer: QgsMapLayer) -> Optional[Self]:

        if isinstance(layer, QgsVectorLayer) and not layer.isSpatial():
            return None

        xt = layer.dataProvider().layerMetadata().extent()
        interval = [[
            DateTime(tr.begin()),
            DateTime(tr.end()),
        ] for tr in xt.temporalExtents() if not tr.isEmpty()]

        if interval:
            return cls(interval=interval)
        else:
            return None


class Extent(extent.Extent):

    @classmethod
    def from_project(cls, p: QgsProject) -> Self:
        return cls(
            spatial=SpatialExtent.from_project(p),
            temporal=TemporalExtent.from_project(p),
        )

    @classmethod
    def from_layer(cls, layer: QgsMapLayer) -> Self:
        return cls(
            spatial=SpatialExtent.from_layer(layer),
            temporal=TemporalExtent.from_layer(layer),
        )
