
import pytest

from pydantic import ValidationError

from qgis.core import (
    Qgis,
    QgsPointXY,
    QgsProcessingParameterCrs,
    QgsProcessingParameterExtent,
    QgsProcessingParameterGeometry,
    QgsProcessingParameterPoint,
    QgsRectangle,
    QgsReferencedGeometry,
    QgsReferencedPointXY,
    QgsReferencedRectangle,
    QgsWkbTypes,
)

from qjazz_processes.processing.inputs import InputParameter
from qjazz_processes.schemas import (
    Formats,
    InputValueError,
    QualifiedInputValue,
)


def test_parameter_point_json(qgis_session):

    param = QgsProcessingParameterPoint("Point")

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_point_json::", schema)

    data = {"coordinates": [4.0, 42.0], "type": "Point"}

    value = inp.value(data)

    assert isinstance(value, QgsPointXY)
    assert value.x() == 4.
    assert value.y() == 42.

    data = {
        "type": "Point",
        "coordinates": [-3326534.0, 5498576.0],
        "crs": {"type": "name", "properties": {"name": "EPSG:3857"}},
    }

    value = inp.value(data)
    assert isinstance(value, QgsReferencedPointXY)
    assert value.x() == -3326534.0
    assert value.y() == 5498576.0
    assert value.crs().authid() == "EPSG:3857"


def test_parameter_point_gml(qgis_session):

    param = QgsProcessingParameterPoint("Point")

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_point_json::", schema)

    data = QualifiedInputValue(
        media_type=Formats.GML.media_type,
        value=(
            '<gml:Point srsName="EPSG:4326">'
            '<gml:coordinates>4,42</gml:coordinates>'
            '</gml:Point>'
        ),
    ).model_dump(mode='json', by_alias=True)

    value = inp.value(data)

    assert isinstance(value, QgsReferencedPointXY)
    assert value.x() == 4.
    assert value.y() == 42.
    assert value.crs().authid() == "EPSG:4326"


def test_parameter_point_wkt(qgis_session):
    """ Test input point from wkt
    """
    param = QgsProcessingParameterPoint("POINT")

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_point_wkt::", schema)

    data = QualifiedInputValue(
        media_type=Formats.WKT.media_type,
        value='CRS=EPSG:4326;POINT(6 10)',
    ).model_dump(mode='json', by_alias=True)

    value = inp.value(data)

    assert isinstance(value, QgsReferencedPointXY)
    assert value.crs().authid() == 'EPSG:4326'
    assert value.asWkt() == "POINT(6 10)"

    # postgis SRID
    data = QualifiedInputValue(
        media_type=Formats.WKT.media_type,
        value='SRID=3785;POINT(365340 3161978)',
    ).model_dump(mode='json', by_alias=True)

    value = inp.value(data)

    assert isinstance(value, QgsReferencedPointXY)
    assert value.crs().authid() == 'EPSG:3785'
    assert value.asWkt() == 'POINT(365340 3161978)'

    # no CRS
    data = QualifiedInputValue(
        media_type=Formats.WKT.media_type,
        value='POINT(6 10)',
    ).model_dump(mode='json', by_alias=True)

    value = inp.value(data)
    assert isinstance(value, QgsPointXY)
    assert value.asWkt() == 'POINT(6 10)'


def test_parameter_geometry_json(qgis_session):
    """ Test passing crs from json
    """
    param = QgsProcessingParameterGeometry("Geometry")

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_geometry_json::", schema)

    data = {
        "type": "Point",
        "coordinates": [445277.96, 5160979.44],
        "crs": {
            "type": "name",
            "properties": {"name": "EPSG:3857"},
        },
    }

    value = inp.value(data)

    assert isinstance(value, QgsReferencedGeometry)
    assert value.crs().authid() == "EPSG:3857"
    assert value.wkbType() == QgsWkbTypes.Point


def test_parameter_geometry_with_types():
    """ Test geometry with paramater types
    """
    # Single geometry type
    param = QgsProcessingParameterGeometry("Geometry", geometryTypes=[Qgis.GeometryType.Line])

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_geometry_with_types::", schema)

    multipoint = {
        "coordinates": [[10, 40], [40, 30], [20, 20], [30, 10]],
        "type": "MultiPoint",
    }

    with pytest.raises(ValidationError):
        _ = inp.value(multipoint)

    # Multi Geometry
    param = QgsProcessingParameterGeometry(
        "Geometry",
        geometryTypes=[Qgis.GeometryType.Line, Qgis.GeometryType.Point],
    )

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_geometry_with_types::", schema)

    value = inp.value(multipoint)
    assert value.wkbType() == QgsWkbTypes.MultiPoint


def test_parameter_crs(qgis_session):
    """ Test CRS input
    """
    param = QgsProcessingParameterCrs("Crs")

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_crs::", schema)

    value = inp.value("EPSG:3857")
    assert value.authid() == "EPSG:3857"

    value = inp.value("urn:ogc:def:crs:OGC:1.3:CRS84")
    assert value.authid() == "OGC:CRS84"

    with pytest.raises(InputValueError):
        _ = inp.value("Foobar")


def test_parameter_extent(qgis_session):

    param = QgsProcessingParameterExtent("Extent")

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_crs::", schema)

    assert schema['format'] == 'ogc-bbox'


def test_parameter_extent_with_default(qgis_session):

    param = QgsProcessingParameterExtent(
        "Extent",
        defaultValue=QgsRectangle(15, 50, 16, 51),
    )

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_crs::", schema)

    assert schema['format'] == 'ogc-bbox'
    assert schema['default'] == {
        'bbox': [15.0, 50.0, 16.0, 51.0],
        'crs': 'urn:ogc:def:crs:OGC:1.3:CRS84',
    }

    data = schema['default']

    value = inp.value(data)

    assert isinstance(value, QgsReferencedRectangle)
    assert value.crs().authid() == 'OGC:CRS84'
