from functools import cache
from typing import Optional, Self

# from pyproj
from qgis.core import QgsCoordinateReferenceSystem

from ..core import crs


@cache
def urn_to_gqis_crs(urn: str) -> QgsCoordinateReferenceSystem:
    return QgsCoordinateReferenceSystem.fromOgcWmsCrs(urn)


class CrsRef(crs.CrsRef):

    @classmethod
    def from_qgis(cls, inp: QgsCoordinateReferenceSystem) -> Optional[Self]:
        if inp.isValid():
            uri = inp.toOgcUri()
            if uri:
                return cls(uri)
        return None

    def to_qgis(self) -> QgsCoordinateReferenceSystem:
        return urn_to_gqis_crs(self.to_ogc_urn())

    @classmethod
    def default(cls) -> Self:
        return cls(crs.WGS84)


def Crs(inp: QgsCoordinateReferenceSystem) -> Optional[crs.Crs]:
    if inp.isValid():
        # XXX QGIS does not give the possibility to export
        # WKT json encoded
        # Workaround using pyproj:
        #   returnreturn pyproj.CRS.from_wkt(inp.toWKT()).to_json_dict()
        return CrsRef.from_qgis(inp) or {'crs_wkt': inp.toWKT()}
    else:
        return CrsRef.default()
