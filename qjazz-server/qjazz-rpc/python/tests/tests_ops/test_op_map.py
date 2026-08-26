"""Tests for `qjazz_rpc.op_map`

The OGC api 'map' request handler completes a partial WMS `GetMap`
query string with the missing required parameters (crs, bbox, width,
height and layers).
"""

from typing import Optional
from urllib.parse import parse_qs

import pytest

from qjazz_core.qgis import Server

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

from qjazz_rpc.op_map import (
    DEFAULT_WIDTH,
    MapRequest,
    bbox_inv_aspect_ratio,
    get_crs,
    lazy,
    prepare_map_request,
    visible_layers,
)

CRS84 = "OGC:CRS84"


#
# Helpers
#


def options_params(options: str) -> dict:
    """Return the parsed query string of a completed request"""
    return {k: v[0] for k, v in parse_qs(options).items()}


def make_project(
    crs: str = "EPSG:3857",
    crs_list: Optional[list[str]] = None,
    extent: Optional[list[str]] = None,
    max_width: Optional[int] = None,
) -> QgsProject:
    """Build an in-memory project with WMS server properties

    `QgsServerProjectUtils` reads the WMS capabilities from the
    project entries, so writing them gives us full control over
    the branches taken by `prepare_map_request`.
    """
    project = QgsProject()
    project.setCrs(QgsCoordinateReferenceSystem.fromOgcWmsCrs(crs))
    # `None` means 'leave the Qgis defaults', an empty list means
    # 'no advertised crs at all'
    if crs_list is not None:
        project.writeEntry("WMSCrsList", "/", crs_list)
    if extent is not None:
        project.writeEntry("WMSExtent", "/", extent)
    if max_width is not None:
        project.writeEntry("WMSMaxWidth", "/", max_width)
    return project


def add_layer(project: QgsProject, name: str, points: str, crs: str = "EPSG:4326") -> QgsVectorLayer:
    """Add a memory point layer holding `points` to the project"""
    layer = QgsVectorLayer(f"Point?crs={crs}", name, "memory")
    assert layer.isValid()

    features = []
    for point in points.split(";"):
        x, y = (float(v) for v in point.split(","))
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        features.append(feature)

    provider = layer.dataProvider()
    assert provider is not None
    assert provider.addFeatures(features)
    layer.updateExtents()

    project.addMapLayer(layer)
    return layer


#
# lazy
#


def test_op_map_lazy_is_called_once():
    calls = []

    def f(value: int) -> int:
        calls.append(value)
        return value

    wrapper = lazy(f, 42)
    assert calls == []
    assert wrapper() == 42
    assert wrapper() == 42
    assert calls == [42]


#
# get_crs
#


def test_op_map_get_crs_from_advertised_list(qgis_server: Server):
    project = make_project(crs="EPSG:4326", crs_list=["EPSG:3857"])
    assert get_crs(project).authid() == "EPSG:3857"


def test_op_map_get_crs_skip_invalid_advertised_crs(qgis_server: Server):
    """Qgis does not validate the advertised crs list: garbage is skipped"""
    project = make_project(crs_list=["", "I am not a crs", "EPSG:2154"])
    assert get_crs(project).authid() == "EPSG:2154"


def test_op_map_get_crs_default_to_crs84(qgis_server: Server):
    """Fall back on CRS84 (conformance) when no advertised crs is usable

    Note: `wmsOutputCrsList` never returns an empty list (it defaults to
    the project crs), so the fallback is only reached when every
    advertised crs is invalid.
    """
    project = make_project(crs="EPSG:2154", crs_list=["not-a-crs"])
    assert get_crs(project).authid() == CRS84


#
# bbox_inv_aspect_ratio
#


def test_op_map_bbox_inv_aspect_ratio():
    assert bbox_inv_aspect_ratio({"bbox": ["0,0,40,20"]}) == 0.5
    assert bbox_inv_aspect_ratio({"bbox": ["0,0,20,40"]}) == 2.0
    # Negative coordinates: only the absolute span matters
    assert bbox_inv_aspect_ratio({"bbox": ["-40,-20,0,0"]}) == 0.5


#
# visible_layers
#


def test_op_map_visible_layers(qgis_server: Server):
    project = make_project()
    add_layer(project, "visible_layer", "0,0;1,1")
    hidden = add_layer(project, "hidden_layer", "0,0;1,1")

    root = project.layerTreeRoot()
    assert root is not None
    node = root.findLayer(hidden.id())
    assert node is not None
    node.setItemVisibilityChecked(False)

    assert list(visible_layers(project)) == ["visible_layer"]


def test_op_map_visible_layers_empty_project(qgis_server: Server):
    assert list(visible_layers(make_project())) == []


#
# prepare_map_request
#


def test_op_map_prepare_all_defaults(qgis_server: Server):
    """Nothing given: crs, bbox, width, height and layers are completed"""
    project = make_project(
        crs="EPSG:3857",
        crs_list=["EPSG:3857"],
        extent=["0", "0", "400", "200"],
    )
    add_layer(project, "layer1", "0,0;1,1")

    req = prepare_map_request(project, "")
    assert isinstance(req, MapRequest)

    assert req.headers["Content-Crs"] == "[EPSG:3857]"
    assert req.headers["Content-Bbox"] == "0.0,0.0,400.0,200.0"

    params = options_params(req.options)
    assert params["crs"] == "EPSG:3857"
    assert params["bbox"] == "0.0,0.0,400.0,200.0"
    # No WMSMaxWidth: default width, height from the inverse aspect ratio
    assert params["width"] == str(DEFAULT_WIDTH)
    assert params["height"] == str(int(DEFAULT_WIDTH * 0.5))
    assert params["layers"] == "layer1"


def test_op_map_prepare_crs_given(qgis_server: Server):
    """A given crs is advertised in CURIE notation"""
    project = make_project(extent=["0", "0", "400", "200"])

    req = prepare_map_request(project, "crs=EPSG:3857")
    assert req.headers["Content-Crs"] == "[EPSG:3857]"
    # The crs is not appended twice
    assert parse_qs(req.options)["crs"] == ["EPSG:3857"]


def test_op_map_prepare_crs_given_as_uri(qgis_server: Server):
    """An http uri is passed through unchanged (no CURIE brackets)"""
    project = make_project(extent=["0", "0", "400", "200"])

    uri = "http://www.opengis.net/def/crs/EPSG/0/3857"
    req = prepare_map_request(project, f"crs={uri}")
    assert req.headers["Content-Crs"] == uri


def test_op_map_prepare_bbox_given(qgis_server: Server):
    """A given bbox is echoed and drives the aspect ratio"""
    project = make_project(crs_list=["EPSG:3857"], extent=["0", "0", "400", "200"])

    req = prepare_map_request(project, "bbox=0,0,100,400")

    assert req.headers["Content-Bbox"] == "0,0,100,400"

    params = options_params(req.options)
    # The project extent is *not* used
    assert params["bbox"] == "0,0,100,400"
    assert params["width"] == str(DEFAULT_WIDTH)
    assert params["height"] == str(int(DEFAULT_WIDTH * 4.0))


def test_op_map_prepare_bbox_from_max_width(qgis_server: Server):
    project = make_project(crs_list=["EPSG:3857"], extent=["0", "0", "400", "200"], max_width=800)

    params = options_params(prepare_map_request(project, "").options)
    assert params["width"] == "800"
    assert params["height"] == "400"


def test_op_map_prepare_width_given(qgis_server: Server):
    """Only the height is computed"""
    project = make_project(crs_list=["EPSG:3857"], extent=["0", "0", "400", "200"])

    params = options_params(prepare_map_request(project, "width=600").options)
    assert params["width"] == "600"
    assert params["height"] == "300"


def test_op_map_prepare_height_given(qgis_server: Server):
    """Only the width is computed"""
    project = make_project(crs_list=["EPSG:3857"], extent=["0", "0", "400", "200"])

    params = options_params(prepare_map_request(project, "height=300").options)
    assert params["width"] == "600"
    assert params["height"] == "300"


def test_op_map_prepare_width_and_height_given(qgis_server: Server):
    """Nothing is computed"""
    project = make_project(crs_list=["EPSG:3857"], extent=["0", "0", "400", "200"])

    options = prepare_map_request(project, "width=123&height=456").options
    params = options_params(options)
    assert params["width"] == "123"
    assert params["height"] == "456"
    assert parse_qs(options)["width"] == ["123"]
    assert parse_qs(options)["height"] == ["456"]


def test_op_map_prepare_inverted_axis(qgis_server: Server):
    """EPSG:4326 is north/east ordered: the extent is inverted"""
    project = make_project(
        crs="EPSG:3857",
        crs_list=["EPSG:4326"],
        # In the project crs (EPSG:3857)
        extent=["0", "0", "400000", "200000"],
    )

    output_crs = QgsCoordinateReferenceSystem.fromOgcWmsCrs("EPSG:4326")
    assert output_crs.hasAxisInverted()

    req = prepare_map_request(project, "")
    assert req.headers["Content-Crs"] == "[EPSG:4326]"

    params = options_params(req.options)
    xmin, ymin, xmax, ymax = (float(v) for v in params["bbox"].split(","))
    # Latitude first: the project extent is twice as wide as it is high,
    # so the *latitude* span comes out as the smaller one
    assert (xmin, ymin) == pytest.approx((0.0, 0.0))
    assert xmax < ymax
    # `r.width()` now holds the latitude span, hence the ratio inversion
    assert int(params["height"]) == int(DEFAULT_WIDTH * (xmax - xmin) / (ymax - ymin))


def test_op_map_prepare_extent_from_layers(qgis_server: Server):
    """No WMSExtent: the extent is computed from the layers"""
    project = make_project(crs="EPSG:4326", crs_list=["EPSG:4326"])
    add_layer(project, "layer1", "0,0;10,20", crs="EPSG:4326")

    req = prepare_map_request(project, "")

    xmin, ymin, xmax, ymax = (float(v) for v in options_params(req.options)["bbox"].split(","))
    # EPSG:4326 has its axis inverted: (lat, lon)
    assert (xmin, ymin, xmax, ymax) == pytest.approx((0.0, 0.0, 20.0, 10.0))


def test_op_map_prepare_layers_given(qgis_server: Server):
    """A given layers parameter is left untouched"""
    project = make_project(crs_list=["EPSG:3857"], extent=["0", "0", "400", "200"])
    add_layer(project, "layer1", "0,0;1,1")

    options = prepare_map_request(project, "layers=other_layer").options
    assert parse_qs(options)["layers"] == ["other_layer"]


def test_op_map_prepare_no_visible_layers(qgis_server: Server):
    """No visible layer: no `layers` parameter is added"""
    project = make_project(crs_list=["EPSG:3857"], extent=["0", "0", "400", "200"])

    options = prepare_map_request(project, "").options
    assert "layers" not in parse_qs(options)


#
# Real project
#


def test_op_map_prepare_from_project_file(qgis_project: QgsProject):
    """Complete a request from the `france_parts` project"""
    req = prepare_map_request(qgis_project, "")

    # The project advertises EPSG:3857
    assert req.headers["Content-Crs"] == "[EPSG:3857]"
    assert "Content-Bbox" in req.headers

    params = options_params(req.options)
    assert params["crs"] == "EPSG:3857"
    assert params["bbox"] == req.headers["Content-Bbox"]
    assert int(params["width"]) == DEFAULT_WIDTH
    assert int(params["height"]) > 0
    # All layers of the tree root are visible
    assert params["layers"].split(",") == [
        "france_parts bordure",
        "france_parts",
        "france_parts tuilé en cache",
    ]
