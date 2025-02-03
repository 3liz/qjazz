#
# STAC provider definition
#
# https://github.com/radiantearth/stac-spec/blob/master/collection-spec/collection-spec.md#provider-object
#
from typing import Literal, Sequence

from pydantic import HttpUrl

from qjazz_contrib.core.models import (
    Field,
    JsonModel,
    Opt,
)


class Provider(JsonModel):

    name: str = Field(
        description="The name of the organization or the individual.",
    )

    description: Opt[str] = Field(
        description="""
        Multi-line description to add further provider information such
        as processing details for processors and producers,
        hosting details for hosts or basic contact information.

        CommonMark 0.29 syntax MAY be used for rich text representation.
        """,
    )

    roles: Sequence[
        Literal[
            "licensor",
            "producer",
            "processor",
            "host",
        ],
    ] = Field(description="Role of the provider")

    url: Opt[HttpUrl] = Field(
        description="""
            Homepage on which the provider describes the dataset
            and publishes contact information.
        """,
    )
