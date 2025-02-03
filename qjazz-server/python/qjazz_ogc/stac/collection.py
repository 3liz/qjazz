#
# STAC Collection
#
# STAC specifications
# See https://github.com/radiantearth/stac-spec/blob/master/collection-spec/collection-spec.md
#
#

from typing import (
    Dict,
    List,
    Literal,
    Sequence,
)

from qjazz_contrib.core.models import (
    Field,
    JsonDict,
    Opt,
)

from ..core.extent import Extent
from ..stac import (
    CatalogBase,
    Provider,
    Range,
)
from .links import Link


class Collection(CatalogBase):

    # Override
    type: Literal["Collection"] = "Collection"

    attribution: Opt[str] = Field(description="attribution for the collection")

    # Use OGC extent definition
    extent: Extent

    keywords: Sequence[str] = ()

    # https://github.com/radiantearth/stac-spec/blob/master/commons/common-metadata.md#licensing
    licence: str = Field("other")   # Required

    providers: Sequence[Provider] = ()

    summaries: Dict[str, Range | JsonDict] = Field({})

    links: List[Link] = Field([])
