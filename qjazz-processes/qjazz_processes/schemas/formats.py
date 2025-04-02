# List of known complex data formats
# you can use any other, but thise are widly known and supported by popular
# software packages
# based on Web Processing Service Best Practices Discussion Paper, OGC 12-029
# http://opengeospatial.org/standards/wps

import mimetypes
import re

from dataclasses import dataclass
from typing import (
    NamedTuple,
    Optional,
    Self,
    cast,
)

SERVICE_MATCH = re.compile(r"^application/x-ogc-(wms|wcs|wfs|wmts)\+xml")
VERSION_MATCH = re.compile(r";\s+version=([^;\s]+)")


@dataclass
class Format:
    media_type: str
    suffix: str
    title: str = ""

    def __eq__(self, other: object) -> bool:
        return self.media_type == cast(Self, other).media_type

    @staticmethod
    def service(media_type: str) -> Optional[str]:
        """Extract ows service from media_type"""
        m = SERVICE_MATCH.match(media_type)
        return m.group(1).upper() if m else None

    @staticmethod
    def version(media_type: str) -> Optional[str]:
        """Extract ows  service version from media_type"""
        m = VERSION_MATCH.match(media_type)
        return m.group(1) if m else None


class _Formats(NamedTuple):
    ANY: Format = Format("application/octet-stream", "")
    WKT: Format = Format("application/wkt", ".wkt", "WKT")
    GEOJSON: Format = Format("application/vnd.geo+json", ".geojson", "GeoJson")
    JSON: Format = Format("application/json", ".json", "Json")
    SHP: Format = Format("application/x-zipped-shp", ".zip", "ESRI Shapefile")
    GML: Format = Format("application/gml+xml", ".gml", "GML")
    GEOTIFF: Format = Format("image/tiff; subtype=geotiff", ".tif", "GeoTiff")
    WCS: Format = Format("application/x-ogc-wcs+xml", ".xml", "WCS")
    WCS100: Format = Format("application/x-ogc-wcs+xml; version=1.0.0", ".xml", "WCS version 1.0.0")
    WCS110: Format = Format("application/x-ogc-wcs+xml; version=1.1.0", ".xml", "WCS version 1.1.0")
    WCS20: Format = Format("application/x-ogc-wcs+xml; version=2.0", ".xml", "WCS version 2.0")
    WFS: Format = Format("application/x-ogc-wfs+xml", ".xml", "WFS")
    WFS100: Format = Format("application/x-ogc-wfs+xml; version=1.0.0", ".xml", "WFS 1.0.0")
    WFS110: Format = Format("application/x-ogc-wfs+xml; version=1.1.0", ".xml", "WFS 1.1.0")
    WFS20: Format = Format("application/x-ogc-wfs+xml; version=2.0", ".xml", "WFS 2.0")
    WMS: Format = Format("application/x-ogc-wms+xml", ".xml", "WMS")
    WMS100: Format = Format("application/x-ogc-wms+xml; version=1.0.0", ".xml", "WMS 1.0.0")
    WMS110: Format = Format("application/x-ogc-wms+xml; version=1.1.0", ".xml", "WMS 1.1.0")
    WMS111: Format = Format("application/x-ogc-wms+xml; version=1.1.1", ".xml", "WMS 1.1.1")
    WMS130: Format = Format("application/x-ogc-wms+xml; version=1.3.0", ".xml", "WMS 1.3.0")
    WMTS: Format = Format("application/x-ogc-wmts+xml;", ".xml", "WMTS")
    WMTS100: Format = Format("application/x-ogc-wmts+xml; version=1.0.0", ".xml", "WMTS 1.0.0")
    TEXT: Format = Format("text/plain", "txt", "Text")
    NETCDF: Format = Format("application/netcdf", ".nc", "NetCDF")
    DXF: Format = Format("application/x-dxf", ".dxf", "Autodesk DXF")
    GPKG: Format = Format("application/geopackage+sqlite3", ".gpkg", "GeoPackage")
    # According to OGC best practices
    # http://www.opengis.net/doc/wps1.0-best-practice-dp
    # naming schema is x-ogc-<gdal code lower case>
    FLATGEOBUF: Format = Format("application/x-ogc-fgb", ".fgb", "FlatGeobuf")
    # OGC API
    FEATURES: Format = Format("application/x-ogc-features+json", ".json", "OGC API Features")


Formats = _Formats()  # type: ignore [call-arg]


def _get_mimetypes():
    mimetypes.init()
    for f in Formats:
        # Add new suffixes (without overriding)
        if f.suffix and f.suffix not in mimetypes.types_map:
            mimetypes.add_type(f.media_type, f.suffix)


_get_mimetypes()
