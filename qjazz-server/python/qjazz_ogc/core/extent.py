'''
OGC Extend

Schema: https://schemas.opengis.net/ogcapi/maps/part1/1.0/openapi/schemas/common-geodata/
'''
from datetime import datetime
from typing import (
    Annotated,
    Literal,
    Sequence,
)

from annotated_types import Len

from qjazz_contrib.core.models import (
    Field,
    JsonModel,
    Nullable,
    OneOf,
    Opt,
)

from .crs import Crs

#
#  Spatial
#

# BBox coordinate sequence
# May be 2D or 2D + vertical axis

Extent2D = Annotated[Sequence[float], Len(min_length=4, max_length=4)]
Extent3D = Annotated[Sequence[float], Len(min_length=6, max_length=6)]

Bbox = OneOf[Extent2D | Extent3D]


class SpatialExtent(JsonModel):
    bbox: Sequence[Bbox] = Field(
        min_length=1,
        description="""
          One or more bounding boxes that describe the spatial extent of the dataset.

          The first bounding box describes the overall spatial
          extent of the data. All subsequent bounding boxes describe
          more precise bounding boxes, e.g., to identify clusters of data.
          Clients only interested in the overall spatial extent will
          only need to access the first item in each array.
        """,
    )
    crs: Opt[Crs] = Field(
        description="""
          Coordinate reference system of the coordinates of the `bbox` property.
          The default reference system is WGS 84 longitude/latitude.
          WGS 84 longitude/latitude/ellipsoidal height for coordinates with height.
          For non-terrestrial coordinate reference system, another CRS may be specified.
        """,
    )
    storage_crs_bbox: Opt[Sequence[Bbox]] = Field(
        min_length=1,
        description="""
          One or more bounding boxes that describe the spatial extent
          of the dataset in the storage (native) CRS (`storageCrs` property).

          The first bounding box describes the overall spatial
          extent of the data. All subsequent bounding boxes describe
          more precise bounding boxes, e.g., to identify clusters of data.
          Clients only interested in the overall spatial extent will
          only need to access the first item in each array.
        """,
    )


Interval = Annotated[
    Sequence[Nullable[datetime]],
    Field(
        min_length=2,
        max_length=2,
        description="""
            Begin and end times of the time interval. The timestamps are in the
            temporal coordinate reference system specified in `trs`. By default
            this is the Gregorian calendar, expressed using RFC 3339 section 5.6.
            Note that these times may be specified using time zone offsets to
            UTC time other than zero.

            The value `null` for start or end time is supported and indicates
            a half-bounded time interval.
        """,
    ),
]

#
# Temporal
#


class TemporalExtent(JsonModel):
    interval: Sequence[Interval] = Field(
        min_length=1,
        description="""
          One or more time intervals that describe the temporal extent of the dataset.
          In the Core only a single time interval is supported.

          Extensions may support multiple intervals.
          The first time interval describes the overall
          temporal extent of the data. All subsequent time intervals describe
          more precise time intervals, e.g., to identify clusters of data.
          Clients only interested in the overall extent will only need
          to access the first item in each array.
        """,
    )
    trs: Literal[
        'http://www.opengis.net/def/uom/ISO-8601/0/Gregorian',
    ] = 'http://www.opengis.net/def/uom/ISO-8601/0/Gregorian'


class Extent(JsonModel):
    spatial: Opt[SpatialExtent] = Field(
        description="The spatial extend of the data in the collection.",
    )
    temporal: Opt[TemporalExtent] = Field(
        description="The temporal extent of the features in the collection.",
    )
