from dataclasses import dataclass
from enum import Enum
from typing import Optional

from qjazz_processes.schemas import Format, OutputFormat


@dataclass(frozen=True)
class WfsOutputDefn:
    """Format available for exporting data."""

    title: str
    media_type: str
    suffix: str
    crs: Optional[str] = None
    ogr_provider: Optional[str] = None
    ogr_options: tuple = ()
    auxiliary_files: tuple = ()
    archive: bool = False

    def as_format(self):
        return Format(self.media_type, self.suffix, self.title)

    def is_native(self) -> bool:
        """Return true if this is a format handled natively by qgis server"""
        return self.ogr_provider is None


class WfsOutputFormat(Enum):
    @classmethod
    def find_format(cls, fmt: OutputFormat) -> Optional["WfsOutputFormat"]:
        for member in cls:
            if member.value.media_type == fmt.media_type:
                return member
        return None

    """ Output formats. """
    SHP = WfsOutputDefn(
        title="ESRI Shapefile",
        media_type="application/x-zipped-shp",
        suffix=".shp",
        ogr_provider="ESRI Shapefile",
        archive=True,
        auxiliary_files=("*.shx", "*.dbf", "*.prj", "*.cpg"),
    )
    TAB = WfsOutputDefn(
        title="Mapinfo (tab)",
        media_type="application/x-zipped-tab",
        suffix=".tab",
        ogr_provider="Mapinfo File",
        archive=True,
        auxiliary_files=("*.dat", "*.map", "*.id"),
    )
    MIF = WfsOutputDefn(
        title="Mapinfo (mif)",
        media_type="application/x-zipped-mif",
        suffix=".mif",
        ogr_provider="Mapinfo File",
        ogr_options=("FORMAT=MIF",),
        auxiliary_files=("*.mid",),
    )
    KML = WfsOutputDefn(
        title="Google earth KML file",
        media_type="application/vnd.google-earth.kml+xml",
        suffix=".kml",
        crs="EPSG:4326",
        ogr_provider="KML",
    )
    GPKG = WfsOutputDefn(
        title="Geopackage",
        media_type="application/geopackage+sqlite3",
        suffix=".gpkg",
        ogr_provider="GPKG",
    )
    GPX = WfsOutputDefn(
        title="GPX",
        media_type="application/gpx+xml",
        suffix=".gpx",
        crs="EPSG:4326",
        ogr_provider="GPX",
        ogr_options=(
            "GPX_USE_EXTENSIONS=YES",
            "GPX_EXTENSIONS_NS=ogr",
            "GPX_EXTENSION_NS_URL=http://osgeo.org/gdal",
        ),
    )
    ODS = WfsOutputDefn(
        title="Open Document Spreadsheet (.ods)",
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        suffix=".ods",
        ogr_provider="ODS",
    )
    XLSX = WfsOutputDefn(
        title="Office Document Spreadsheet (.xlsx)",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        suffix=".xlsx",
        ogr_provider="XLSX",
    )
    CSV = WfsOutputDefn(
        title="CSV",
        media_type="text/csv",
        suffix=".csv",
        ogr_provider="CSV",
    )
    FGB = WfsOutputDefn(
        title="FlatGeobuf",
        media_type="application/x-fgb",
        suffix=".fgb",
        ogr_provider="FlatGeobuf",
    )
    #
    # Standard format returned by GetFeature requests
    #
    JSON = WfsOutputDefn(
        title="GeoJSON",
        media_type="application/geo+json",
        suffix=".geojson",
    )
    GML2 = WfsOutputDefn(
        title="Geographic Markup Language, version 2)", media_type="text/xml; subtype=gml/2.1.2", suffix=".gml"
    )
    GML3 = WfsOutputDefn(
        title="Geographic Markup Language, version 3)", media_type="text/xml; subtype=gml/3.1.1", suffix=".gml"
    )
