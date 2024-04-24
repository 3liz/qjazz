#
# OGC bounding box
#

from annotated_types import Len
from typing_extensions import (
    Annotated,
    List,
    Sequence,
)

from .models import JsonModel
from .ogc import CrsRef

Coordinates2D = Annotated[List[float], Len(min_length=4, max_length=4)]
Coordinates3D = Annotated[List[float], Len(min_length=6, max_length=6)]


class BoundinBox(JsonModel):
    bbox: Coordinates2D | Coordinates3D
    crs: CrsRef | Sequence[CrsRef] = CrsRef.wgs84()
