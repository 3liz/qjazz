
# List of known complex data formats
# you can use any other, but thise are widly known and supported by popular
# software packages
# based on Web Processing Service Best Practices Discussion Paper, OGC 12-029
# http://opengeospatial.org/standards/wps

import mimetypes

from typing_extensions import NamedTuple, Optional


class Format(NamedTuple):
    media_type: str
    suffix: str
    schema: Optional[str] = None


class _Formats(NamedTuple):
    ANY: Format = Format('application/octet-stream', '', None)
    WKT: Format = Format('application/wkt', '.wkt', None)
    GEOJSON: Format = Format('application/vnd.geo+json', '.geojson', None)
    JSON: Format = Format('application/json', '.json', None)
    SHP: Format = Format('application/x-zipped-shp', '.zip', None)
    GML: Format = Format('application/gml+xml', '.gml', None)
    GEOTIFF: Format = Format('image/tiff; subtype=geotiff', '.tif', None)
    WCS: Format = Format('application/xogc-wcs', '.xml', None)
    WCS100: Format = Format('application/x-ogc-wcs; version=1.0.0', '.xml', None)
    WCS110: Format = Format('application/x-ogc-wcs; version=1.1.0', '.xml', None)
    WCS20: Format = Format('application/x-ogc-wcs; version=2.0', '.xml', None)
    WFS: Format = Format('application/x-ogc-wfs', '.xml', None)
    WFS100: Format = Format('application/x-ogc-wfs; version=1.0.0', '.xml', None)
    WFS110: Format = Format('application/x-ogc-wfs; version=1.1.0', '.xml', None)
    WFS20: Format = Format('application/x-ogc-wfs; version=2.0', '.xml', None)
    WMS: Format = Format('application/x-ogc-wms', '.xml', None)
    WMS130: Format = Format('application/x-ogc-wms; version=1.3.0', '.xml', None)
    WMS110: Format = Format('application/x-ogc-wms; version=1.1.0', '.xml', None)
    WMS100: Format = Format('application/x-ogc-wms; version=1.0.0', '.xml', None)
    TEXT: Format = Format('text/plain', 'txt', None)
    NETCDF: Format = Format('application/netcdf', '.nc', None)
    DXF: Format = Format('application/x-dxf', '.dxf', None)
    # According to OGC best practices
    # http://www.opengis.net/doc/wps1.0-best-practice-dp
    # naming schema is x-ogc-<gdal code lower case>
    FLATGEOBUF: Format = Format('application/x-ogc-flatgeobuf', '.fgb', None)
    GPKG: Format = Format('application/x-ogc-gpkg', '.gpkg', None)


Formats = _Formats()  # type: ignore [call-arg]


def _get_mimetypes():
    mimetypes.init()
    for f in Formats:
        # Add new suffixes (without overriding)
        if f.suffix and f.suffix not in mimetypes.types_map:
            mimetypes.add_type(f.media_type, f.suffix)


_get_mimetypes()
