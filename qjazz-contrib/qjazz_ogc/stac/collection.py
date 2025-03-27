#
# STAC Collection
#
# STAC specifications
# See https://github.com/radiantearth/stac-spec/blob/master/collection-spec/collection-spec.md
#
#

from typing import (
    Literal,
    Sequence,
)

from qjazz_contrib.core.models import (
    Field,
    JsonDict,
    Option,
)

from ..core.extent import Extent
from ..stac import (
    CatalogBase,
    Provider,
    Range,
)


class Collection(CatalogBase):
    # Override
    type: Literal["Collection"] = "Collection"

    attribution: Option[str] = Field(description="attribution for the collection")

    # Use OGC extent definition
    extent: Extent

    keywords: Sequence[str] = ()

    # https://github.com/radiantearth/stac-spec/blob/master/commons/common-metadata.md#licensing
    licence: str = Field("other")  # Required

    providers: Sequence[Provider] = ()

    summaries: dict[str, Range | JsonDict] = Field({})
