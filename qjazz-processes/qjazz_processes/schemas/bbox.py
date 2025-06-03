#
# OGC bounding box
#
from typing import (
    Annotated,
    Optional,
    Sequence,
    TypeAlias,
)

from annotated_types import Len
from pydantic import Field

from .crs import CrsDefinition
from .models import JsonModel, OneOf
from .ogc import WGS84

Extent2D = Annotated[Sequence[float], Len(min_length=4, max_length=4)]
Extent3D = Annotated[Sequence[float], Len(min_length=6, max_length=6)]

BboxCoordinates = OneOf[Extent2D | Extent3D]


# OGC bounding box definition
# See https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/bbox.yaml
def BoundingBox(default: Optional[str] = None) -> TypeAlias:

    class BBox(JsonModel):
        bbox: BboxCoordinates
        crs: CrsDefinition = Field(default or WGS84)  # type: ignore [valid-type]

    return BBox

