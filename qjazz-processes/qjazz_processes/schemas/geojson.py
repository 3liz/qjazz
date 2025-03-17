from typing import (
    Annotated,
    Literal,
    Optional,
    Self,
    Sequence,
    Union,
)

from pydantic import Field

from .models import JsonModel, OneOf
from .ogc import WGS84

POINT = "Point"
MULTIPOINT = "MultiPoint"
LINESTRING = "LineString"
MULTILINESTRING = "MultiLineString"
POLYGON = "Polygon"
MULTIPOLYGON = "MultiPolygon"
GEOMETRY_COLLECTION = "GeometryCollection"


class _Named(JsonModel):
    name: str


# Geojson CRS definition
class NamedCrs(JsonModel):
    type: Literal["name"] = "name"
    properties: _Named = Field(default=_Named(name=WGS84))

    @classmethod
    def from_ref(cls, ref: str) -> Self:
        return cls(properties=_Named(name=ref))

    def name(self) -> str:
        return self.properties.name


class Referenced(JsonModel):
    crs: Optional[NamedCrs] = None


# Point

PointItem = Annotated[Sequence[float], Field(min_length=2, max_length=4)]


class Point(Referenced):
    type: Literal[POINT]  # type: ignore [valid-type]
    coordinates: PointItem

    @classmethod
    def from_xy(cls, x: float, y: float) -> Self:
        return cls(type=POINT, coordinates=(x, y))


class MultiPoint(Referenced):
    type: Literal[MULTIPOINT]  # type: ignore [valid-type]
    coordinates: Sequence[PointItem]


# LineString


LineStringItem = Annotated[Sequence[PointItem], Field(min_length=2, max_length=2)]


class LineString(Referenced):
    type: Literal[LINESTRING]  # type: ignore [valid-type]
    coordinates: LineStringItem


class MultiLineString(Referenced):
    type: Literal[MULTILINESTRING]  # type: ignore [valid-type]
    coordinates: Sequence[LineStringItem]


# Polygon

Ring = Annotated[Sequence[PointItem], Field(min_length=4)]
PolygonItem = Sequence[Ring]


class Polygon(Referenced):
    type: Literal[POLYGON]  # type: ignore [valid-type]
    coordinates: PolygonItem


class MultiPolygon(Referenced):
    type: Literal[MULTIPOLYGON]  # type: ignore [valid-type]
    coordinates: Sequence[PolygonItem]


# Geometry


class GeometryCollection(Referenced):
    type: Literal[GEOMETRY_COLLECTION]  # type: ignore [valid-type]
    geometries: Sequence["Geometry"]


Geometry = OneOf[
    Union[
        Point,
        MultiPoint,
        LineString,
        MultiLineString,
        Polygon,
        MultiPolygon,
        GeometryCollection,
    ]
]
