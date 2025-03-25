"""
Links as specified in
https://github.com/radiantearth/stac-spec/blob/master/commons/links.md
"""

from pydantic import HttpUrl

from qjazz_contrib.core.models import (
    Field,
    JsonModel,
    Option,
)


class Link(JsonModel):
    href: HttpUrl
    rel: str
    media_type: Option[str] = Field(alias="type")
    title: Option[str] = None
    description: Option[str] = None
    templated: Option[bool] = None
    hreflang: Option[str] = None
