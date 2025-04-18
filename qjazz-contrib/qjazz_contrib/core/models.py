from textwrap import dedent
from typing import (
    Annotated,
    Any,
    TypeAlias,
    TypeVar,
    cast,
)

import pydantic

from pydantic import (
    BaseModel,
    JsonValue,
    alias_generators,
)
from pydantic.aliases import PydanticUndefined


# noqa ANN401
def Field(
    default: Any = PydanticUndefined,  # noqa ANN401
    *,
    description: str | None = None,
    **kwargs,
) -> Any:  # noqa ANN401
    return pydantic.Field(
        default,
        description=dedent(description.removeprefix("\n")) if description else None,
        **kwargs,
    )


#
model_json_properties = dict(
    alias_generator=alias_generators.to_camel,
    populate_by_name=True,
)

JsonDict: TypeAlias = dict[str, JsonValue]


# Ensure that union type use `OneOf` in schema
# instead of `anyOf`

# See https://github.com/pydantic/pydantic/issues/656#


def one_of(s):
    if "anyOf" in s:
        s["oneOf"] = s["anyOf"]
        del s["anyOf"]


# Example: OneOf[str|int] will produce:
# {'oneOf': [{'type': 'string'}, {'type': 'integer'}]} instead of:
# {'anyOf': ... }

T = TypeVar("T")

OneOf: TypeAlias = Annotated[T, pydantic.Field(json_schema_extra=one_of)]


#
# Recursively remove autogenerated title from
# schema properties
#
def remove_auto_title(schema: JsonDict):
    match schema:
        case {"type": "object", "properties": dict(props)}:
            for k, v in props.items():
                v = cast(JsonDict, v)
                _pull_title(k, v)
                remove_auto_title(v)
        case {"oneOf": seq} | {"allOf": seq} | {"anyOf": seq}:
            for v in cast(list, seq):
                remove_auto_title(cast(JsonDict, v))
    if "$defs" in schema:
        for k, v in cast(JsonDict, schema["$defs"]).items():
            v = cast(JsonDict, v)
            _pull_title(k, v)
            remove_auto_title(v)


def _pull_title(k: str, v: JsonDict):
    title = v.get("title")
    if title and cast(str, title).lower().replace(" ", "_") == k.lower():
        v.pop("title")


#
# Fix optional field in json_schema
#
# This will replace schema for Optional[T] as
# { 'type': ..., ... } instead of
# { 'anyof': [{ 'type': ..., ,,,}, { 'type': null }] }
#
def fix_optional_schema(s):
    schema = s.pop("anyOf")[0]
    s.pop("default", None)
    s.update(schema)


def fix_nullable_schema(s):
    fix_optional_schema(s)
    s.update(nullable=True)


Option = Annotated[T | None, Field(default=None, json_schema_extra=fix_optional_schema)]

# nullable = true
Nullable = Annotated[T | None, Field(json_schema_extra=fix_nullable_schema)]

# Json base model


class JsonModel(BaseModel, **model_json_properties):
    @classmethod
    def model_json_schema(cls, *args, **kwargs) -> JsonDict:
        schema = super(JsonModel, cls).model_json_schema(*args, **kwargs)
        remove_auto_title(schema)
        return schema

    # Override: force by_alias=True
    def model_dump_json(self, *args, **kwargs) -> str:
        return super().model_dump_json(*args, by_alias=True, exclude_none=True, **kwargs)
