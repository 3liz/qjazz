import mimetypes

from typing import (
    Annotated,
    Literal,
    Optional,
    Protocol,
    Self,
    Type,
    TypeAlias,
    cast,
)

from pydantic import (
    AnyHttpUrl,
    AnyUrl,
    JsonValue,
    TypeAdapter,
    ValidationError,
)

from qjazz_contrib.core.condition import assert_precondition
from qjazz_contrib.core.models import (
    Field,
    JsonDict,
    JsonModel,
    OneOf,  # noqa F401
    Option,  # noqa F401
    one_of,  # noqa F401
    remove_auto_title,  # noqa F401
)


class _LinkBase(JsonModel):
    # The type or semantics of the relation.
    rel: Option[str] = None
    # Mime type of the data returne by the link
    mime_type: Option[str] = Field(serialization_alias="type")
    # human-readable identifier for the link
    title: str = ""
    # A long description for the link
    description: Option[str] = None
    # Estimated size (in bytes) of the online resource response
    length: Option[int] = None
    # Is the link templated with '{?<keyword>}'
    templated: bool = False
    # Language of the resource referenced
    hreflang: Option[str] = None


#
#  Generic link
#
class Link(_LinkBase):
    # Supplies the URI to a remote resource (or resource fragment).
    href: str = Field(json_schema_extra={"format": "uri-reference"})


#
# Define HTTP link
#
class LinkHttp(_LinkBase):
    href: AnyHttpUrl


#
# Extented link reference for input/output
# by reference
#
class LinkReference(LinkHttp):
    # Http method
    method: Literal["GET", "POST"] = "GET"
    # Request body
    body: Option[str] = None


class MediaTypeProtocol(Protocol):
    @property
    def media_type(self) -> str: ...


def MediaType(
    _type: Type,
    media_type: str,
    *,
    encoding: Optional[str] = None,
    schema: Optional[str] = None,
) -> TypeAlias:
    schema_extra: dict = {"contentMediaType": media_type}
    if encoding:
        schema_extra.update(contentEncoding=encoding)
    if schema:
        schema_extra.update(contentSchema=schema)

    return Annotated[_type, Field(json_schema_extra=schema_extra)]


class OutputFormat(JsonModel):
    media_type: str
    encoding: Option[str] = None
    schema_: Option[AnyUrl | JsonDict] = Field(alias="schema")

    def __eq__(self, other: object) -> bool:
        return self.media_type == cast(MediaTypeProtocol, other).media_type


class QualifiedInputValue(OutputFormat):
    value: JsonValue


# Create a typeadapter for Reference/Qualified input


RefOrQualifiedInput: TypeAdapter = TypeAdapter(QualifiedInputValue | LinkReference)

#
# Mixin class for handling output format in
# input parameters with auto-created output -
# like destination parameters
#

AnyFormat = OutputFormat(media_type="application/octet-stream")


class OutputFormatDefinition:
    _output_format: OutputFormat = AnyFormat
    _output_ext: str = ""

    @property
    def output_format(self) -> OutputFormat:
        return self._output_format

    @output_format.setter
    def output_format(self, value: OutputFormat):
        self._output_format = value
        if value.media_type == AnyFormat.media_type:
            self.extension = ""
        else:
            self._output_ext = mimetypes.guess_extension(value.media_type) or ""

    @property
    def output_extension(self) -> str:
        return self._output_ext

    @output_extension.setter
    def output_extension(self, ext: str):
        assert_precondition(ext.startswith("."), "Suffix should start with a '.'")
        self._output_ext = ext
        media_type = mimetypes.types_map.get(ext)
        self._output_format = OutputFormat(media_type=media_type) if media_type else AnyFormat

    def copy_format_from(self, other: Self):
        self._output_format = other._output_format
        self._output_ext = other._output_ext


#
# Input error
#


class InputValueError(Exception):
    def __init__(
        self,
        msg: str,
        details: Optional[ValidationError] = None,
    ):
        if details:
            text = details.json(
                include_url=False,
                include_context=False,
                include_input=False,
            )
            super().__init__(f'{{ "message": "{msg}", "details": {text} }}')
        else:
            super().__init__(msg)
