
from collections.abc import Sequence
from typing import (
    Iterator,
    Optional,
    Self,
    cast,
)

from qjazz_ogc.extent import parse_bbox, transform_extent

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsPrintLayout,
    QgsProject,
)
from qgis.server import QgsServerProjectUtils

from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import assert_precondition
from qjazz_processes.schemas import (
    JsonModel,
    Option,
)
from qjazz_processes.schemas.bbox import Extent2D

#
# Composer layouts
#


class MapLayoutItem(JsonModel):
    ident: str
    name: str
    selectable_layers: bool
    extent: Option[Extent2D]
    width: float
    heigth: float


class Composer(JsonModel):
    name: str
    width: float
    heigth: float
    units: str = "mm"
    atlas_enabled: bool
    atlas_coverage_layer: Option[str] = None
    crs: str
    maps: Sequence[MapLayoutItem]
    labels: Sequence[str]

    @classmethod
    def from_layout(
        cls,
        project: QgsProject,
        layout: QgsPrintLayout,
    ) -> Self:

        # From server/services/wms/qgswmsgetcapabilities.cpp
        layout_size = layout.pageCollection().page(0).sizeWithUnits()
        width = layout.convertFromLayoutUnits(layout_size.width(), Qgis.LayoutUnit.Millimeters)
        height = layout.convertFromLayoutUnits(layout_size.height(), Qgis.LayoutUnit.Millimeters)

        atlas = layout.atlas()
        atlas_coverage_layer = None
        if atlas:
            layout = atlas.layout()
            atlas_enabled = atlas.enabled()
            coverage_layer = atlas.coverageLayer()
            if coverage_layer:
                if QgsServerProjectUtils.wmsUseLayerIds(project):
                    atlas_coverage_layer = coverage_layer.id()
                else:
                    atlas_coverage_layer = coverage_layer.serverProperties().shortName()
                    if not atlas_coverage_layer:
                        atlas_coverage_layer = coverage_layer.name()
        else:
            atlas_enabled = False

        crs = project.crs()
        if not crs.isValid():
            crs = "OGC:CRS84"
        else:
            crs = crs.authid()

        return cls(
            name=layout.name(),
            width=width.length(),
            heigth=height.length(),
            atlas_enabled=atlas_enabled,
            atlas_coverage_layer=atlas_coverage_layer,
            maps=tuple(get_map_layout_items(project, layout)),
            crs=crs,
            labels=tuple(filter(
                None,
                (item.id() for item in layout.items() if isinstance(item, QgsLayoutItemLabel))
            ))
        )


def get_composers(project: QgsProject) -> Iterator[Composer]:
    restricted_composers = set(QgsServerProjectUtils.wmsRestrictedComposers(project))
    manager = project.layoutManager()
    return (Composer.from_layout(project, layout) for layout in manager.printLayouts()
        if layout.name() not in restricted_composers)

#
# Map layout items
#


def get_map_layout_items_for(
    project: QgsProject,
    template: str,
    output_crs: Optional[QgsCoordinateReferenceSystem] = None,
) -> Iterator[MapLayoutItem]:

    layout = project.layoutManager().layoutByName(template)
    yield from get_map_layout_items(project, layout, output_crs)


def get_map_layout_items(
    project: QgsProject,
    layout: QgsPrintLayout,
    output_crs: Optional[QgsCoordinateReferenceSystem] = None,
) -> Iterator[MapLayoutItem]:

    assert_precondition(isinstance(layout, QgsPrintLayout))
    output_crs = cast(QgsCoordinateReferenceSystem, output_crs or project.crs())

    index = 0
    for item in layout.items():
        if not isinstance(item, QgsLayoutItemMap):
            continue

        extent = item.extent()
        if not extent.isEmpty():
            # Remap the extent
            crs = item.presetCrs()
            if crs and crs.authid() != output_crs.authid():
                extent = transform_extent(extent, crs, output_crs, project)

            bbox = parse_bbox(extent, output_crs.hasAxisInverted())
        else:
            logger.warning("Null extent for map layout '%s'", item.id())
            bbox = None

        rect = item.rect()

        yield MapLayoutItem(
            ident=f"map{index}",
            name=item.displayName(),
            selectable_layers=not bool(item.layers()),
            width=rect.width(),
            heigth=rect.height(),
            extent=bbox,
        )

        index += 1
