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
from .models import JsonValue, MediaType, OneOf, Field


UriCrsDefinition = Annotated[AnyUrl, Field(json_schema_extra={ "format": "uri" })]


# NOTE: CRS schema is still an open question about WKT naming
# See https://github.com/opengeospatial/ogcapi-tiles/issues/170
#
# The wkt naming is confusing so we dont use it as specified
# in the draft
#
# As an alternative, we support WKT as string with content mediaType.
#
PROJJSON_SCHEMA_REF="https://proj.org/en/latest/schemas/v0.7/projjson.schema.json"

CrsDefinition = OneOf[  # type: ignore [misc, valid-type]
    Union[
        str,
        UriCrsDefinition,
        MediaType(str, Formats.WKT.media_type),
        MediaType(
            str, 
            Formats.JSON.media_type, 
            schema=f'{{ "$ref": "{PROJJSON_SCHEMA_REF}" }}',
        ),
    ],
]
