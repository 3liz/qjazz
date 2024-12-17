
import pytest

from pydantic import TypeAdapter, ValidationError

from qjazz_processes.schemas import geojson
from qjazz_processes.schemas.geojson import (
    Geometry,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)


def test_geojson_point():

    ta = TypeAdapter(Point)

    # schema = ta.json_schema()

    p = ta.validate_python({
            'type': 'Point',
            'coordinates': (1.0, 1.0),
        })

    print("\n", p)

    assert isinstance(p, Point)
    assert p.type == geojson.POINT
    assert len(p.coordinates) == 2


def test_geojson_invalid_type():

    ta = TypeAdapter(Point)

    with pytest.raises(ValidationError):
        # Bad 'type' : Point expected
        ta.validate_python({
            'type': 'LineString',
            'coordinates': (1.0, 1.0),
        })


def test_geojson_multipoint():

    ta = TypeAdapter(MultiPoint)

    # schema = ta.json_schema()
    # assert schema['type'] == geojson.MULTIPOINT

    mp = ta.validate_python({
            'type': 'MultiPoint',
            'coordinates': ((1.0, 1.0), (2.0, 2.0), (3.0, 3.0)),
        })

    print("\n", mp)

    assert isinstance(mp, MultiPoint)
    assert mp.type == geojson.MULTIPOINT
    assert len(mp.coordinates) == 3


def test_geojson_linestring():

    ta = TypeAdapter(LineString)

    # schema = ta.json_schema()

    ls = ta.validate_python({
            'type': 'LineString',
            'coordinates': ((1.0, 1.0), (1.0, 1.0)),
        })

    print("\n", ls)

    assert isinstance(ls, LineString)
    assert ls.type == geojson.LINESTRING
    assert len(ls.coordinates) == 2


def test_geojson_multilinestring():

    ta = TypeAdapter(MultiLineString)

    # schema = ta.json_schema()

    ml = ta.validate_python({
            'type': 'MultiLineString',
            'coordinates': (
                ((1.0, 1.0), (2.0, 2.0)),
                ((2.0, 1.0), (2.0, 4.0)),
            ),
        })

    print("\n", ml)

    assert isinstance(ml, MultiLineString)
    assert ml.type == geojson.MULTILINESTRING
    assert len(ml.coordinates) == 2


def test_geojson_polygon():

    ta = TypeAdapter(Polygon)

    # schema = ta.json_schema()

    # Note: Only the schema is checked
    # no validity of the geometry is
    # tested

    pl = ta.validate_python({
            'type': 'Polygon',
            'coordinates': (
                ((1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (1.0, 1.0)),
                ((0.5, 0.5), (2.0, 4.0), (2.5, 2.5), (0.5, 0.5)),
            ),
        })

    print("\n", pl)

    assert isinstance(pl, Polygon)
    assert pl.type == geojson.POLYGON
    assert len(pl.coordinates) == 2

    with pytest.raises(ValidationError):
        # Invalid polygon with invalid ring
        ta.validate_python({
            'type': 'Polygon',
            'coordinates': (
                ((1.0, 1.0), (3.0, 3.0), (1.0, 1.0)),
                ((0.5, 0.5), (2.0, 4.0), (2.5, 2.5), (0.5, 0.5)),
            ),
        })


def test_geojson_multipolygon():

    ta = TypeAdapter(MultiPolygon)

    # schema = ta.json_schema()

    # Note: Only the schema is checked
    # not the validity of the geometry

    pl = ta.validate_python({
            'type': 'MultiPolygon',
            'coordinates': (
                (
                    ((1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (1.0, 1.0)),
                    ((0.5, 0.5), (2.0, 4.0), (2.5, 2.5), (0.5, 0.5)),
                ),
                (
                    ((1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (1.0, 1.0)),
                    ((0.5, 0.5), (2.0, 4.0), (2.5, 2.5), (0.5, 0.5)),
                ),
            ),
        })

    print("\n", pl)

    assert isinstance(pl, MultiPolygon)
    assert pl.type == geojson.MULTIPOLYGON
    assert len(pl.coordinates) == 2


def test_geojson_geometry():
    """ Test Union geometry alias
    """
    ta = TypeAdapter(Geometry)

    print("\n", ta.json_schema())

    g = ta.validate_python({
        'type': 'LineString',
        'coordinates': ((1.0, 1.0), (1.0, 1.0)),
    })

    print(g)
    assert isinstance(g, LineString)

    g = ta.validate_python({'type': 'Point', 'coordinates': (1.0, 1.0)})
    print(g)
    assert isinstance(g, Point)
