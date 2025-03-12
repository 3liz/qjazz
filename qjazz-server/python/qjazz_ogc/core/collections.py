#
# Collections
#
# OGC Specifications
# See https://schemas.opengis.net/ogcapi/maps/part1/1.0/openapi/schemas/common-geodata/collectionDesc.yaml
#
# STAC specifications
# See https://github.com/radiantearth/stac-spec/blob/master/collection-spec/collection-spec.md
#
#
from datetime import datetime as DateTimeType
from typing import Sequence

from qjazz_contrib.core.models import (
    Field,
    Opt,
)

from ..stac import collection
from .crs import CRS84, Crs


class Collection(collection.Collection):

    # XXX Check specs for this, this is totally unclear how it relates
    # to spatial extent `crs`
    crs: Opt[list[Crs]] = Field(
        default=[CRS84],
        description="""
            the list of coordinate reference systems supported by the API;
            the first item is the default coordinate reference system
        """,
    )

    storage_crs: Opt[Crs] = Field(
        description="""
            the native coordinate reference system (i.e., the most efficient CRS in
            which to request the data, possibly how the data is stored on the server);
            this is the default output coordinate reference system
            for Maps and Coverages
        """,
    )

    geometry_dimension: Opt[int] = Field(
        description="""
            The geometry dimension of the features shown in this layer (
            0: points, 1: curves, 2: surfaces, 3: solids), unspecified: mixed or unknown'
        """,
        ge=0,
        le=3,
    )

    min_scale_denominator: Opt[float] = Field(
        description="Minimum scale denominator for usage of the collection",
    )
    max_scale_denominator: Opt[float] = Field(
        description="Maximum scale denominator for usage of the collection",
    )

    # Extensions to OGC schema

    # Not required for STAC collection object
    # but they are qgis project metadata
    datetime: Opt[DateTimeType] = Field(description="DateTime associated no this resource")
    created: Opt[DateTimeType] = Field(description="Creation DateTime")
    updated: Opt[DateTimeType] = Field(description="Update DateTime")

    # QJazz Addition
    copyrights: Opt[Sequence[str]] = None
