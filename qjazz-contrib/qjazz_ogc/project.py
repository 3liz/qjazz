"""
QGIS project's collections
"""

from typing import (
    Iterator,
    Optional,
    Self,
    Sequence,
)

from pydantic import HttpUrl

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsMapLayer,
    QgsProject,
)
from qgis.server import QgsServerProjectUtils

from qjazz_contrib.core.models import Option

from .core import collections
from .core.crs import Crs
from .crs import Crs3D, CrsRef
from .extent import Extent
from .layers import LayerAccessor
from .metadata import DateTime, Keywords, Links
from .stac import links


def output_crs_list(p: QgsProject) -> Iterator[Crs]:
    # The spec says that the first CRS in the list should
    # be the native one. But since QGIS users have full control
    # over the configuration, we let that choice to the project owner.
    # Note that an empty list will default to CRS84
    for crsdef in QgsServerProjectUtils.wmsOutputCrsList(p):
        output_crs = CrsRef.from_qgis(QgsCoordinateReferenceSystem.fromOgcWmsCrs(crsdef))
        if output_crs:
            yield output_crs


def scale_denominators(p: QgsProject) -> tuple[Optional[float], Optional[float]]:
    """Compute scale denominator"""
    scales: tuple[float, float] | None = None

    for ml in LayerAccessor(p).layers():
        if ml.hasScaleBasedVisibility():
            if not scales:
                scales = (ml.minimumScale(), ml.maximumScale())
            else:
                scales = (
                    max(ml.minimumScale(), scales[0]),
                    min(ml.maximumScale(), scales[1]),
                )

    return scales if scales else (None, None)


def get_layer_short_name(layer: QgsMapLayer) -> str:
    """Get the layer name according if the shortname is set"""
    if Qgis.QGIS_VERSION_INT < 33800:
        name = layer.shortName()
    else:
        name = layer.serverProperties().shortName()
    if not name:
        name = layer.name()

    return name


class Collection(collections.Collection):
    # Not included in schemas but passed to
    # map proxy
    styles: Option[Sequence[str]] = None
    legend_url: Option[HttpUrl] = None
    legend_format: Option[str] = None

    #
    # Compute catalog entry form QGIS project
    #

    @classmethod
    def from_project(cls, ident: str, p: QgsProject) -> Self:
        """Build a Collection from a QGIS project"""
        md = p.metadata()

        title = QgsServerProjectUtils.owsServiceTitle(p)
        if title in ("", "Untitled"):
            title = md.title() or "Untitled"

        abstract = QgsServerProjectUtils.owsServiceAbstract(p) or md.abstract()
        keywords = QgsServerProjectUtils.owsServiceKeywords(p) or Keywords(md)

        attribution = QgsServerProjectUtils.owsServiceContactOrganization(p) or None

        min_scale, max_scale = scale_denominators(p)
        crs_outputs = tuple(output_crs_list(p))

        return cls(
            id=ident,
            title=title,
            description=abstract,
            attribution=attribution,
            extent=Extent.from_project(p),
            datetime=DateTime(md.dateTime(Qgis.MetadataDateType.Published)),
            updated=DateTime(md.dateTime(Qgis.MetadataDateType.Revised)),
            created=DateTime(md.dateTime(Qgis.MetadataDateType.Created)),
            crs=crs_outputs,
            storage_crs=Crs3D(p),
            keywords=keywords,
            links=Links(md),
            min_scale_denominator=min_scale,
            max_scale_denominator=max_scale,
        )

    #
    # Compute catalog entry form QGIS layer
    #

    @classmethod
    def from_layer(cls, layer: QgsMapLayer, parent: Self) -> Self:
        """Build a Collection from a QGIS project"""

        provider = layer.dataProvider()
        md = provider.layerMetadata()

        # XXX Create an SPDX AND expression for all licences in list
        licence = " AND ".join(md.licenses()) or "other"

        if Qgis.QGIS_VERSION_INT < 33800:
            title = layer.title()
            abstract = layer.abstract()
            attribution = layer.attribution()
            attribution_url = layer.attributionUrl()
            keywords = layer.keywordList()
        else:
            props = layer.serverProperties()
            title = props.title()
            abstract = props.abstract()
            attribution = props.attribution()
            attribution_url = props.attributionUrl()
            keywords = props.keywordList()

        def layer_links() -> Iterator[links.Link]:
            if attribution_url:
                yield links.Link(
                    href=attribution_url,
                    rel="external",
                    title="Attribution url",
                )

        crs_outputs: Optional[list[Crs]] = None
        storage_crs: Optional[Crs] = None
        min_scale_denominator: Optional[float] = None
        max_scale_denominator: Optional[float] = None

        extent = Extent.from_layer(layer)
        if extent.spatial:
            # Crs outputs are inherited from parents
            storage_crs = Crs3D(layer)
            crs_outputs = parent.crs
            if layer.hasScaleBasedVisibility():
                (min_scale_denominator, max_scale_denominator) = (
                    layer.minimumScale(),
                    layer.maximumScale(),
                )

        styles = layer.styleManager().styles()
        # Only default style
        if not styles or len(styles) == 1:
            styles = None
        legend_url = layer.legendUrl() or None
        legend_format = layer.legendUrlFormat() or None

        return cls(
            id=layer.name(),
            title=title,
            description=abstract,
            attribution=attribution,
            licence=licence,
            extent=extent,
            datetime=DateTime(provider.dataTimestamp()),
            updated=None,
            created=None,
            crs=crs_outputs,
            storage_crs=storage_crs,
            keywords=[kw for kw in keywords.split(",") if kw],
            links=[link for link in layer_links()],
            min_scale_denominator=min_scale_denominator,
            max_scale_denominator=max_scale_denominator,
            # Additions to STAC specs
            copyrights=md.rights(),
            styles=styles,
            legend_url=legend_url,
            legend_format=legend_format,
        )
