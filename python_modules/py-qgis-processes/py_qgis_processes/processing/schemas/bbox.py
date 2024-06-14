#
# OGC bounding box
#
from annotated_types import Len
from pydantic import Field
from typing_extensions import (
    Annotated,
    Optional,
    Sequence,
    TypeAlias,
)

from .models import JsonModel, OneOf
from .ogc import WGS84

Coordinates2D = Annotated[Sequence[float], Len(min_length=4, max_length=4)]
Coordinates3D = Annotated[Sequence[float], Len(min_length=6, max_length=6)]

BboxCoordinates = OneOf[Coordinates2D | Coordinates3D]


# OGC bounding box definition
# See https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/bbox.yaml
def BoundingBox(crsdef: Optional[TypeAlias] = None) -> TypeAlias:

    if not crsdef:
        crsdef = Annotated[str, Field(WGS84)]

    class _BBox(JsonModel):
        bbox: BboxCoordinates
        crs: crsdef    # type: ignore [valid-type]

    return Annotated[
        _BBox,
        Field(
            title="OGCboundingbox",
            json_schema_extra={'format': 'ogc-bbox'},
        ),
    ]
