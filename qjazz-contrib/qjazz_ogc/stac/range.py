"""
Range definition
See https://github.com/radiantearth/stac-spec/blob/master/collection-spec/collection-spec.md#range-object
"""

from qjazz_contrib.core.models import (
    JsonModel,
)


class Range(JsonModel):
    minimum: float | str
    maximum: float | str
