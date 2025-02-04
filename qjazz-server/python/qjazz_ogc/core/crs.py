'''
CRS schema

See https://schemas.opengis.net/ogcapi/maps/part1/1.0/openapi/schemas/common-geodata/crs.yaml
'''
from typing import Optional, Self, Union

from pydantic import HttpUrl

from qjazz_contrib.core.models import JsonDict


class CrsRef(HttpUrl):

    @classmethod
    def from_authority(
        cls,
        name: str,
        code: int | str,
        *,
        version: Optional[str] = None,
        url_prefix: str = "https://www.opengis.net",
    ) -> Self:
        # Version is not required
        if version:
            return cls(f"{url_prefix}/def/crs/{name}/{version}/{code}")
        else:
            return cls(f"{url_prefix}/def/crs/{name}/{code}")

    @classmethod
    def from_epsg_code(cls, code: int | str) -> Self:
        return cls.from_authority("EPSG", code)

    def to_ogc_urn(self) -> str:
        return f"urn:ogc{(self.path or "").replace('/', ':')}"  #


WGS84 = CrsRef.from_authority("OGC", "CRS84", version="1.3")
WGS84h = CrsRef.from_authority("OGC", "CRS84h", version="0")


Crs = Union[CrsRef, JsonDict]
