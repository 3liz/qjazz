#
# OGC Crs schema
#

from typing import (
    Annotated,
    TypedDict,
    Union,
)

from pydantic import AnyUrl, WithJsonSchema

from .formats import Formats
from .models import JsonValue, MediaType, OneOf


class UriCrsDefinition(TypedDict):
    uri: AnyUrl


class JsonCrsDefinition(TypedDict):
    json: Annotated[
        JsonValue,
        WithJsonSchema(
            {
                "type": "object",
                "description": "ProjJSON CRS definition",
                "$ref": (
                    "https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi"
                    "/schemas/common-geodata/projJSON.yaml"
                ),
            },
        ),
    ]


# NOTE: CRS schema is still an open question about WKT naming
# See https://github.com/opengeospatial/ogcapi-tiles/issues/170
#
# The wkt naming is confusing so we dont use it as specified
# in the draft
#
# As an alternative, we support WKT as string with content mediaType.
#

CrsDefinition = OneOf[  # type: ignore [misc, valid-type]
    Union[
        str,
        MediaType(str, Formats.WKT.media_type),
        UriCrsDefinition,
        JsonCrsDefinition,
    ],
]
