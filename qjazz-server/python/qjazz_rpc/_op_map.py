#
# OGC api 'map' request
#
from dataclasses import dataclass
from typing import Any, Callable, Iterator
from urllib.parse import parse_qs

from qjazz_ogc.crs import CrsRef
from qjazz_ogc.extent import compute_extent_from_layers, transform_extent

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProject,
)
from qgis.server import QgsServerProjectUtils

from qjazz_contrib.core import logger

DEFAULT_WITH = 1024


class InvalidMapRequest(Exception):
    pass


def lazy[**P, T](f: Callable[P, T], *args, **kwargs) -> Callable[[], T]:
    value: T | None = None

    def wrapper() -> T:
        nonlocal value
        if not value:
            value = f(*args, **kwargs)
        return value

    return wrapper


def get_crs(p: QgsProject) -> QgsCoordinateReferenceSystem:
    # Check from advertised crs list
    crs_list = QgsServerProjectUtils.wmsOutputCrsList(p)
    if crs_list:
        return QgsCoordinateReferenceSystem.fromOgcWmsCrs(crs_list[0])
    else:
        # Default to CRS84 (conformance)
        return CrsRef.default().to_qgis()


def bbox_inv_aspect_ratio(params):
    bbox = params["bbox"][0]
    c = tuple(float(x) for x in bbox.split(","))
    return abs(c[3] - c[2]) / abs(c[1] - c[0])


def visible_layers(p: QgsProject) -> Iterator[str]:
    for item in p.layerTreeRoot().children():
        if item.isVisible():
            yield item.name()


@dataclass
class MapRequest:
    headers: dict[str, str]
    options: str


def prepare_map_request(project: QgsProject, options: str) -> MapRequest:
    """Check for missing required parameters for
    a proper WMS GetMap request

    Assume that all given values are valid as validation
    occured from the client. Otherwise this will trigeer a 500
    internal error.

    See: https://docs.qgis.org/latest/en/docs/server_manual/services/wms.html#wms-getmap
    """

    params: Any = parse_qs(options)
    headers: dict[str, str] = {}

    logger.debug("Preparing map request: %s", params)

    crs = lazy(get_crs, project)

    # NOTE: A bbox should never be set without a crs !!

    # See https://docs.ogc.org/pol/09-048r6.html#toc14 for CURIE notation
    if "crs" not in params:
        content_crs = crs().authid()
        headers["Content-Crs"] = f"[{content_crs}]"  # CURIE notation
        options = f"{options}&crs={content_crs}"
    else:
        content_crs = params[0]
        headers["Content-Crs"] = content_crs if content_crs.startswith("http") else f"[{content_crs}]"

    if "bbox" not in params:
        # wmsExtent is assumed to be in project crs.
        output_crs = crs()
        r = QgsServerProjectUtils.wmsExtent(project)
        if r.isEmpty():
            r = compute_extent_from_layers(project, output_crs)
        else:
            r = transform_extent(r, project.crs(), output_crs, project)

        # Assume version 1.3.0
        if output_crs.hasAxisInverted():  # Inversion east/north, long/lata
            r.invert()

        content_bbox = f"{r.xMinimum()},{r.yMinimum()},{r.xMaximum()},{r.yMaximum()}"
        options = f"{options}&bbox={content_bbox}"

        inv_aspect_ratio = lambda: r.height() / r.width()  # noqa E731
    else:
        content_bbox = params["bbox"]
        inv_aspect_ratio = lambda: bbox_inv_aspect_ratio(params)  # noqa E731

    headers["Content-Bbox"] = content_bbox

    width = params.get("width")
    height = params.get("height")

    match (width, height):
        case None, None:
            w = QgsServerProjectUtils.wmsMaxWidth(project)
            if w < 0:
                w = DEFAULT_WITH
            h = int(w * inv_aspect_ratio())
            options = f"{options}&width={w}&height={h}"
        case w, None:
            h = int(w[0] * inv_aspect_ratio())
            options = f"{options}&height={h}"
        case None, h:
            w = int(h[0] / inv_aspect_ratio())
            options = f"{options}&width={w}"

    # No layers set, set all visible layers from  treeRoot
    # otherwise we will have a blank image
    if "layers" not in params:
        layers = ",".join(visible_layers(project))
        if layers:
            options = f"{options}&layers={layers}"

    return MapRequest(headers=headers, options=options)
