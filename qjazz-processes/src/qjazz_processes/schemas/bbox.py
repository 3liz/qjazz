#
# OGC bounding box
#
from typing import (
    Annotated,
    Any,
    Optional,
    Sequence,
)

from annotated_types import Len
from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema

from .models import JsonModel, OneOf
from .ogc import WGS84

Extent2D = Annotated[Sequence[float], Len(min_length=4, max_length=4)]
Extent3D = Annotated[Sequence[float], Len(min_length=6, max_length=6)]

BboxCoordinates = OneOf[Extent2D | Extent3D]


# OGC bounding box definition
# See https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/bbox.yaml
class BBox(JsonModel):
    bbox: BboxCoordinates
    crs: str = WGS84


def BoundingBox(default: Optional[str] = None) -> type[BBox]:
    """Return a BBox model with `default` as default crs"""
    if not default or default == WGS84:
        return BBox

    class _BBox(BBox):
        crs: str = default  # type: ignore [assignment]

    _BBox.__name__ = "BBox"
    return _BBox


class DefaultCrs:
    """Annotated metadata for setting the default crs of a BBox

    Usage:
        Annotated[BBox, DefaultCrs(crs)]

    Static type checkers see `BBox`, pydantic use the model
    returned by `BoundingBox(crs)`.
    """

    def __init__(self, crs: Optional[str] = None):
        self.crs = crs

    def __get_pydantic_core_schema__(
        self,
        source: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        return handler(BoundingBox(self.crs))
