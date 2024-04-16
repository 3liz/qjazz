from pydantic import (
    AnyHttpUrl,
    BaseModel,
    Field,
    JsonValue,
    TypeAdapter,
    alias_generators,
)
from typing_extensions import Literal, Optional

JsonValueType = TypeAdapter(JsonValue)

model_json_properties = dict(
    alias_generator=alias_generators.to_camel,
    populate_by_name=True,
)


class JsonModel(BaseModel, **model_json_properties):
    # Override: force by_alias=True
    def model_dump_json(self, *args, **kwargs) -> str:
        return super().model_dump_json(*args, by_alias=True, exclude_none=True, **kwargs)


class ErrorResponse(JsonModel):
    message: str
    details: Optional[JsonValue] = None

    # Conveys an identifier for the link's context.
# See https://www.iana.org/assignments/link-relations/link-relations.xhtml


LinkRel = Literal[
    "self",
    "first",
    "last",
    "next",
    "prev",
    "related",
    "up",
]


class Link(JsonModel):
    # Supplies the URI to a remote resource (or resource fragment).
    href: AnyHttpUrl
    # The type or semantics of the relation.
    rel: str
    # Mime type of the data returne by the link
    mime_type: Optional[str] = Field(default=None, serialization_alias="type")
    # human-readable identifier for the link
    title: str = ""
    # A long description for the link
    description: Optional[str] = None
    # Estimated size (in bytes) of the online resource response
    length: Optional[int] = None
    # Is the link templated with '{?<keyword>}'
    templated: bool = False
    # Language of the resource referenced
    hreflang: Optional[str] = None
