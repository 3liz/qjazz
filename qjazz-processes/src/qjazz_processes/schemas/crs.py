#
# OGC Crs schema
#

from typing import (
    Annotated,
    Union,
)

from pydantic import AnyUrl

from .formats import Formats
from .models import Field, MediaTypeField

UriCrsDefinition = Annotated[AnyUrl, Field(json_schema_extra={"format": "uri"})]


# NOTE: CRS schema is still an open question about WKT naming
# See https://github.com/opengeospatial/ogcapi-tiles/issues/170
#
# The wkt naming is confusing so we dont use it as specified
# in the draft
#
# As an alternative, we support WKT as string with content mediaType.
#
PROJJSON_SCHEMA_REF = "https://proj.org/en/latest/schemas/v0.7/projjson.schema.json"

CrsDefinition = Union[
    str,
    UriCrsDefinition,
    Annotated[str, MediaTypeField(Formats.WKT.media_type)],
    Annotated[
        str,
        MediaTypeField(
            Formats.JSON.media_type,
            schema={"$ref": PROJJSON_SCHEMA_REF},
        ),
    ],
]
