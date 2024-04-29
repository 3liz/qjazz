
from pydantic import AnyUrl
from typing_extensions import NamedTuple

# See http://schemas.opengis.net/ogcapi/features/part1/1.0/openapi/schemas/
OGC_FEATURES_SCHEMA_URL = "https://schemas.opengis.net/ogcapi/features/part1/1.0/opengis/schemas"


class _GeoJSONSchemas(NamedTuple):
    Point = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/pointGeoJSON.yaml")
    MultiPoint = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/multipointGeoJSON.yaml")
    Linestring = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/linestringGeoJSON.yaml")
    MultiLinestring = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/multilinestringGeoJSON.yaml")
    Polygon = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/polygonGeoJSON.yaml")
    MultiPolygon = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/multipolygonGeoJSON.yaml")
    Geometry = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/geometryGeoJSON.yaml")
    GeometryCollection = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/geometrycollectionGeoJSON.yaml")
    Feature = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/featureGeoJSON.yaml")
    FeatureCollection = AnyUrl(f"{OGC_FEATURES_SCHEMA_URL}/featureCollectionGeoJSON.yaml")


GeoJSON = _GeoJSONSchemas()
