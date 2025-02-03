"""
Links as specified in
https://github.com/radiantearth/stac-spec/blob/master/commons/links.md
"""

from pydantic import HttpUrl

from qjazz_contrib.core.models import (
    Field,
    JsonModel,
    Opt,
)


class Link(JsonModel):
    href: HttpUrl
    rel: str
    media_type: Opt[str] = Field(alias="type")
    title: Opt[str] = None
    description: Opt[str] = None
    templated: Opt[bool] = None
    hreflang: Opt[str] = None
