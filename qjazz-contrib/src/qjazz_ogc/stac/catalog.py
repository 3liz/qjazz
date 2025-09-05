"""
STAC Catalog definition

See https://github.com/radiantearth/stac-spec/blob/master/catalog-spec/catalog-spec.md
"""

from typing import (
    Literal,
    Sequence,
)

from qjazz_core.models import (
    Annotated,
    Field,
    JsonModel,
    Option,
)

from .links import Link


class CatalogBase(JsonModel):
    stac_version: Literal["1.0.0"] = "1.0.0"
    stac_extensions: Sequence[Annotated[str, Field(json_schema_extra={"format": "iri"})]] = Field([])

    id: str = Field(description="identifier of the collection used")
    title: Option[str] = Field(description="human readable title of the collection")
    description: str = Field("", description="human readable title of the collection")

    links: list[Link] = Field([])


class Catalog(CatalogBase):
    type: Literal["Catalog"] = "Catalog"
