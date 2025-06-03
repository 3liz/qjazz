#
# Crs schema
#

from typing import (
    Union,
)

from pydantic import AnyUrl

from .formats import Formats
from .models import MediaType, OneOf

CrsDefinition = OneOf[  # type: ignore [misc, valid-type]
    Union[
        str,
        AnyUrl,
        MediaType(str, Formats.WKT.media_type),
        MediaType(str, Formats.GML.media_type),
    ],
]
