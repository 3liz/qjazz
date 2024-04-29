
# List of known complex data formats
# you can use any other, but thise are widly known and supported by popular
# software packages
# based on Web Processing Service Best Practices Discussion Paper, OGC 12-029
# http://opengeospatial.org/standards/wps

from typing_extensions import NamedTuple, Optional


class Format(NamedTuple):
    media_type: str
    suffix: str
    schema: Optional[str]


class _Formats(NamedTuple):
    WKT = Format('application/wkt', '.wkt', None)                          # type: ignore [misc]
    GEOJSON = Format('application/vnd.geo+json', '.geojson', None)         # type: ignore [misc]
    JSON = Format('application/json', '.json', None)                       # type: ignore [misc]
    SHP = Format('application/x-zipped-shp', '.zip', None)                 # type: ignore [misc]
    GML = Format('application/gml+xml', '.gml', None)                      # type: ignore [misc]
    GEOTIFF = Format('image/tiff; subtype=geotiff', '.tiff', None)         # type: ignore [misc]
    WCS = Format('application/xogc-wcs', '.xml', None)                     # type: ignore [misc]
    WCS100 = Format('application/x-ogc-wcs; version=1.0.0', '.xml', None)  # type: ignore [misc]
    WCS110 = Format('application/x-ogc-wcs; version=1.1.0', '.xml', None)  # type: ignore [misc]
    WCS20 = Format('application/x-ogc-wcs; version=2.0', '.xml', None)     # type: ignore [misc]
    WFS = Format('application/x-ogc-wfs', '.xml', None)                    # type: ignore [misc]
    WFS100 = Format('application/x-ogc-wfs; version=1.0.0', '.xml', None)  # type: ignore [misc]
    WFS110 = Format('application/x-ogc-wfs; version=1.1.0', '.xml', None)  # type: ignore [misc]
    WFS20 = Format('application/x-ogc-wfs; version=2.0', '.xml', None)     # type: ignore [misc]
    WMS = Format('application/x-ogc-wms', '.xml', None)                    # type: ignore [misc]
    WMS130 = Format('application/x-ogc-wms; version=1.3.0', '.xml', None)  # type: ignore [misc]
    WMS110 = Format('application/x-ogc-wms; version=1.1.0', '.xml', None)  # type: ignore [misc]
    WMS100 = Format('application/x-ogc-wms; version=1.0.0', '.xml', None)  # type: ignore [misc]
    TEXT = Format('text/plain', '.txt', None)                              # type: ignore [misc]
    NETCDF = Format('application/x-netcdf', '.nc', None)                   # type: ignore [misc]
    ANY = Format('application/octet-stream', '.nc', None)                  # type: ignore [misc]


Formats = _Formats()  # type: ignore [call-arg]
