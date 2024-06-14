
from pydantic import AnyUrl
from typing_extensions import NamedTuple

# See http://schemas.opengis.net/ogcapi/features/part1/1.0/openapi/schemas/
OGC_FEATURES_SCHEMA_URL = "https://schemas.opengis.net/ogcapi/features/part1/1.0/opengis/schemas"


class _GeoJSONSchemas(NamedTuple):
    Point: AnyUrl = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/pointGeoJSON.yaml")
    MultiPoint: AnyUrl = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/multipointGeoJSON.yaml")
    Linestring: AnyUrl = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/linestringGeoJSON.yaml")
    MultiLinestring: AnyUrl = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/multilinestringGeoJSON.yaml")
    Polygon: AnyUrl = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/polygonGeoJSON.yaml")
    MultiPolygon: AnyUrl = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/multipolygonGeoJSON.yaml")
    Geometry: AnyUrl = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/geometryGeoJSON.yaml")
    GeometryCollection: AnyUrl = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/geometrycollectionGeoJSON.yaml")
    Feature: AnyUrl = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/featureGeoJSON.yaml")
    FeatureCollection: AnyUrl = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/featureCollectionGeoJSON.yaml")


GeoJSON = _GeoJSONSchemas()
