"""
QGIS project's collections
"""
from datetime import datetime as DateTimeType
from typing import (
    Iterator,
    Optional,
    Self,
    Tuple,
)

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsProject,
)
from qgis.server import QgsServerProjectUtils

from qjazz_contrib.core.models import Nullable, Opt

from ..core import collections, crs
from .crs import Crs, CrsRef
from .extent import Extent
from .metadata import DateTime, Keywords, Links


def output_crs_list(p: QgsProject) -> Iterator[crs.Crs]:
    storage_wms_crs = Crs(p.crs3D())
    if storage_wms_crs:
        yield storage_wms_crs

    for crsdef in QgsServerProjectUtils.wmsOutputCrsList(p):
        output_crs = CrsRef.from_qgis(QgsCoordinateReferenceSystem.fromOgcWmsCrs(crsdef))
        if output_crs:
            yield output_crs


def scale_denominators(p: QgsProject) -> Tuple[Optional[float], Optional[float]]:
    """ Compute scale denominator
    """
    restricted_layers = QgsServerProjectUtils.wmsRestrictedLayers(p)
    scales: Tuple[float, float] | None = None

    for ml in p.mapLayers().values():
        if ml.name() in restricted_layers:
            continue

        if ml.hasScaleBasedVisibility():
            if not scales:
                scales = (ml.minimumScale(), ml.maximumScale())
            else:
                scales = (
                    min(ml.minimumScale(), scales[0]),
                    max(ml.maximumScale(), scales[1]),
                )

    return scales if scales else (None, None)


class Collection(collections.Collection):

    datetime: Nullable[DateTimeType]
    created: Opt[DateTimeType]
    updated: Opt[DateTimeType]

    @classmethod
    def from_project(cls, ident: str, p: QgsProject) -> Self:
        """ Build a Collection from a QGIS project
        """
        md = p.metadata()

        title = QgsServerProjectUtils.owsServiceTitle(p)
        if title in ("", "Untitled"):
            title = md.title() or "Untitled"

        abstract = QgsServerProjectUtils.owsServiceAbstract(p) or md.abstract()
        keywords = QgsServerProjectUtils.owsServiceKeywords(p) or Keywords(md)

        default_crs = CrsRef.default().to_qgis()

        min_scale, max_scale = scale_denominators(p)

        return cls(
            id=ident,
            title=title,
            description=abstract,
            extent=Extent.from_project(p, default_crs),
            datetime=DateTime(md.dateTime(Qgis.MetadataDateType.Published)),
            updated=DateTime(md.dateTime(Qgis.MetadataDateType.Revised)),
            created=DateTime(md.dateTime(Qgis.MetadataDateType.Created)),
            crs=tuple(output_crs_list(p)),
            storageCrs=Crs(p.crs3D()),
            keywords=keywords,
            links=Links(md),
            min_scale_denominator=min_scale,
            max_scale_denominator=max_scale,
        )
