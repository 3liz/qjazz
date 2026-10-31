import pytest

from pydantic import ValidationError

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsPointXY,
    QgsProcessingParameterCoordinateOperation,
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
from qjazz_processes.processing.inputs.geometry import geojson, qgsgeometry_to_json
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
    assert value.x() == 4.0
    assert value.y() == 42.0

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
        value=('<gml:Point srsName="EPSG:4326"><gml:coordinates>4,42</gml:coordinates></gml:Point>'),
    ).model_dump(mode="json")

    value = inp.value(data)

    assert isinstance(value, QgsReferencedPointXY)
    assert value.x() == 4.0
    assert value.y() == 42.0
    assert value.crs().authid() == "EPSG:4326"

    # Check back to json
    jsonvalue = qgsgeometry_to_json(geojson.Point, value)
    assert jsonvalue.type == "Point"
    assert jsonvalue.crs is not None


def test_parameter_point_wkt(qgis_session):
    """Test input point from wkt"""
    param = QgsProcessingParameterPoint("POINT")

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_point_wkt::", schema)

    data = QualifiedInputValue(
        media_type=Formats.WKT.media_type,
        value="CRS=EPSG:4326;POINT(6 10)",
    ).model_dump(mode="json")

    value = inp.value(data)

    assert isinstance(value, QgsReferencedPointXY)
    assert value.crs().authid() == "EPSG:4326"
    assert value.asWkt() == "POINT(6 10)"

    # postgis SRID
    data = QualifiedInputValue(
        media_type=Formats.WKT.media_type,
        value="SRID=3785;POINT(365340 3161978)",
    ).model_dump(mode="json")

    value = inp.value(data)

    assert isinstance(value, QgsReferencedPointXY)
    assert value.crs().authid() == "EPSG:3785"
    assert value.asWkt() == "POINT(365340 3161978)"

    # no CRS
    data = QualifiedInputValue(
        media_type=Formats.WKT.media_type,
        value="POINT(6 10)",
    ).model_dump(mode="json")

    value = inp.value(data)
    assert isinstance(value, QgsPointXY)
    assert value.asWkt() == "POINT(6 10)"


def test_parameter_referenced_geometry(qgis_session):
    """Test passing crs from json"""
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
    """Test geometry with parameter types"""
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


@pytest.mark.parametrize(
    "value",
    [
        "POINT(1 2)",
        '{"type": "Point", "coordinates": [1, 2]}',
    ],
)
def test_parameter_geometry_bare_string(value):
    """Bare strings must be passed as qualified input"""
    param = QgsProcessingParameterGeometry("Geometry")
    inp = InputParameter(param)

    with pytest.raises(ValidationError):
        inp.value(value)

    media_type = Formats.WKT.media_type if value.startswith("POINT") else Formats.GEOJSON.media_type
    geom = inp.value({"value": value, "mediaType": media_type})
    assert geom.asWkt() == "Point (1 2)"


def test_parameter_geometry_polygon():
    """Test geometry with parameter types"""
    # Single geometry type
    param = QgsProcessingParameterGeometry("Geometry", geometryTypes=[Qgis.GeometryType.Polygon])

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_geometry_polygon::", schema)

    polygon = {
        "coordinates": [[[10, 40], [40, 30], [20, 20], [30, 10], [10, 40]]],
        "type": "Polygon",
    }

    value = inp.value(polygon)
    assert value.wkbType() == QgsWkbTypes.Polygon

    # Check back to json
    jsonvalue = qgsgeometry_to_json(geojson.Polygon, value)
    assert jsonvalue.type == "Polygon"
    assert jsonvalue.crs is None


def test_parameter_crs(qgis_session):
    """Test CRS input"""
    param = QgsProcessingParameterCrs("Crs", defaultValue="EPSG:2154")

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_crs::schema", schema)

    assert "anyOf" in schema
    assert schema["format"] == "x-ogc-crs"

    # contentSchema must be a schema object
    content_schemas = [s["contentSchema"] for s in schema["anyOf"] if "contentSchema" in s]
    assert content_schemas == [
        {"$ref": "https://proj.org/en/latest/schemas/v0.7/projjson.schema.json"},
    ]

    value = inp.value("EPSG:3857")
    assert value.authid() == "EPSG:3857"

    value = inp.value("urn:ogc:def:crs:OGC:1.3:CRS84")
    assert value.authid() == "OGC:CRS84"

    epsg3857 = QgsCoordinateReferenceSystem()
    epsg3857.createFromUserInput("EPSG:3857")
    assert epsg3857.isValid()
    epsg3857_WKT = epsg3857.toWkt()
    print("\ntest_parameter_crs::epsg3857_WKT", epsg3857_WKT)

    value = inp.value(
        {
            "value": epsg3857_WKT,
            "mediaType": Formats.WKT.media_type,
        }
    )
    assert value.isValid()
    assert value.authid() == "EPSG:3857"

    with pytest.raises(InputValueError):
        _ = inp.value("Foobar")


@pytest.mark.parametrize(
    "source,destination",
    [
        ("SOURCE_CRS", "DESTINATION_CRS"),
        ("SOURCE_CRS", ""),
        ("", "DESTINATION_CRS"),
        ("", ""),
    ],
)
def test_parameter_coordinate_operation_metadata(source, destination):
    """Crs parameter names are published as metadata"""
    param = QgsProcessingParameterCoordinateOperation(
        "Operation",
        sourceCrsParameterName=source,
        destinationCrsParameterName=destination,
    )

    metadata = {
        md.role: md.value
        for md in InputParameter(param).description().metadata
        if md.role in ("sourceCrsParameterName", "destinationCrsParameterName")
    }

    expected = {}
    if source:
        expected["sourceCrsParameterName"] = source
    if destination:
        expected["destinationCrsParameterName"] = destination

    assert metadata == expected


@pytest.mark.parametrize(
    "static_crs,expected",
    [
        # No static crs
        ({}, {}),
        (
            {
                "staticSourceCrs": QgsCoordinateReferenceSystem("EPSG:4326"),
                "staticDestinationCrs": QgsCoordinateReferenceSystem("EPSG:3857"),
            },
            {
                "staticSourceCrs": "urn:ogc:def:crs:EPSG::4326",
                "staticDestinationCrs": "urn:ogc:def:crs:EPSG::3857",
            },
        ),
        # Static crs given as string
        ({"staticDestinationCrs": "EPSG:3857"}, {"staticDestinationCrs": "EPSG:3857"}),
    ],
)
def test_parameter_coordinate_operation_static_crs(qgis_session, static_crs, expected):
    """Static crs are published as metadata"""
    param = QgsProcessingParameterCoordinateOperation("Operation", **static_crs)

    metadata = {
        md.role: md.value
        for md in InputParameter(param).description().metadata
        if md.role in ("staticSourceCrs", "staticDestinationCrs")
    }
    assert metadata == expected


def test_parameter_extent(qgis_session):
    param = QgsProcessingParameterExtent("Extent")

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_crs::", schema)

    assert schema["format"] == "ogc-bbox"


@pytest.mark.parametrize(
    "default",
    [
        # Null rectangle (inverted infinite bounds)
        QgsRectangle(),
        # Empty rectangle
        QgsRectangle(1, 1, 1, 1),
    ],
)
def test_parameter_extent_without_valid_default(qgis_session, default):
    """No schema default for a null or empty default extent"""
    param = QgsProcessingParameterExtent("Extent", defaultValue=default)

    schema = InputParameter(param).json_schema()
    assert "default" not in schema


def test_parameter_extent_with_default(qgis_session):
    param = QgsProcessingParameterExtent(
        "Extent",
        defaultValue=QgsRectangle(15, 50, 16, 51),
    )

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_crs::", schema)

    assert schema["format"] == "ogc-bbox"
    assert schema["default"] == {
        "bbox": [15.0, 50.0, 16.0, 51.0],
        "crs": "urn:ogc:def:crs:OGC:1.3:CRS84",
    }

    data = schema["default"]

    value = inp.value(data)

    assert isinstance(value, QgsReferencedRectangle)
    assert value.crs().authid() == "OGC:CRS84"
