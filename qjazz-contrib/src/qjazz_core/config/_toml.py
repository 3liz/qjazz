#
# Output TOML documented default configuration from
# pydantic models
#
# The model is walked recursively:
#
# * Fields whose type is a model (or an optional model) are output
#   as sections (`[a.b]`).
# * Lists of models are output as array of tables (`[[a.b]]`).
# * Dicts of models are output as sections with a placeholder
#   key (`[a.'key']`).
# * All other fields are output as `key = value` with their
#   documentation (title, description and examples) as comments.
#
# Sections for optional models with a `None` default are commented out.
#
import inspect
import json
import math
import re

from collections.abc import Mapping, MutableMapping, MutableSequence, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from dataclasses import field as dc_field
from textwrap import dedent
from types import NoneType, UnionType
from typing import (
    IO,
    Annotated,
    Any,
    Iterator,
    Literal,
    Union,
    get_args,
    get_origin,
)

from pydantic import BaseModel, TypeAdapter
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined, to_jsonable_python

#
# Type introspection
#

_SEQUENCE_TYPES = (list, tuple, set, frozenset, Sequence, MutableSequence, AbstractSet)
_MAPPING_TYPES = (dict, Mapping, MutableMapping)


def _unwrap(t: Any) -> Any:
    """Strip `Annotated` and `type X = ...` aliases

    Nested wrappers are removed until the underlying
    type is reached, i.e `Annotated[MyAlias, ...]` where
    `type MyAlias = int | None` returns `int | None`.
    """
    while True:
        if get_origin(t) is Annotated:
            t = get_args(t)[0]
        elif hasattr(t, "__value__") and not inspect.isclass(t):
            # PEP 695 type alias
            t = t.__value__
        else:
            return t


def _is_model(t: Any) -> bool:
    """Return True if the type is a pydantic model class"""
    return inspect.isclass(t) and issubclass(t, BaseModel)


def _union_members(t: Any) -> tuple[list[Any], bool]:
    """Return the non-None members of a type and whether
    the type is nullable

    Both `Union[...]`/`Optional[...]` and `X | Y` forms are
    handled; nested unions and aliases are flattened.
    A non-union type returns a single member list.
    """
    t = _unwrap(t)
    if get_origin(t) in (Union, UnionType):
        members = []
        nullable = False
        for m in get_args(t):
            sub, is_null = _union_members(m)
            members.extend(sub)
            nullable = nullable or is_null
        return members, nullable
    if t is None or t is NoneType:
        return [], True
    return [t], False


def _models_of(t: Any) -> list[type[BaseModel]] | None:
    """Return the list of models if all non-None members
    of the type are models, None otherwise
    """
    members, _ = _union_members(t)
    if members and all(_is_model(m) for m in members):
        return members
    return None


@dataclass
class _Kind:
    """Classification of a field annotation

    * 'value': plain value, output as `key = value`
    * 'model': model (or union of models), output as `[section]`
    * 'list': sequence of models, output as `[[section]]`
    * 'dict': mapping of models, output as `[section.'key']`

    `models` hold the candidate model classes for non 'value' kinds.
    """

    kind: Literal["value", "model", "list", "dict"]
    models: list[type[BaseModel]] = dc_field(default_factory=list)
    nullable: bool = False


def _field_kind(annotation: Any) -> _Kind:
    """Classify a field annotation for output

    Sequences and mappings are considered as sections only if their
    item (resp. value) type is a model or a union of models;
    otherwise the field is a plain value.
    """
    members, nullable = _union_members(annotation)

    if members and all(_is_model(m) for m in members):
        return _Kind("model", members, nullable)

    if len(members) == 1:
        t = members[0]
        origin = get_origin(t)
        args = get_args(t)
        if origin in _SEQUENCE_TYPES and args:
            # Note: tuple[X, ...] or homogeneous tuple
            item_args = [a for a in args if a is not Ellipsis]
            if len(set(item_args)) == 1:
                models = _models_of(item_args[0])
                if models:
                    return _Kind("list", models, nullable)
        elif origin in _MAPPING_TYPES and len(args) == 2:
            models = _models_of(args[1])
            if models:
                return _Kind("dict", models, nullable)

    return _Kind("value", nullable=nullable)


#
# Value formatting
#

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _format_key(key: str) -> str:
    """Format a TOML key: keys that cannot be written
    as bare keys are double-quoted
    """
    return key if _BARE_KEY.match(key) else json.dumps(key, ensure_ascii=False)


def _format_string(s: str) -> str:
    """Format a TOML string

    Multiline strings are output as literal strings (`'''...'''`)
    when possible, other strings as basic (escaped) strings.
    """
    if "\n" in s and "'''" not in s:
        # Multiline literal string
        return f"'''{s}'''"
    return json.dumps(s, ensure_ascii=False)


def _format_value(v: Any) -> str:
    """Format a json compatible value as a TOML value

    Lists are output as inline arrays and dicts as inline tables;
    `None` items are skipped since TOML has no null value.
    Unknown types are output as their string representation.
    """
    match v:
        case bool(b):
            return "true" if b else "false"
        case int(n):
            return str(n)
        case float(f):
            if math.isnan(f):
                return "nan"
            if math.isinf(f):
                return "inf" if f > 0 else "-inf"
            return repr(f)
        case str(s):
            return _format_string(s)
        case list(items):
            return "[" + ", ".join(_format_value(i) for i in items if i is not None) + "]"
        case dict(d):
            if not d:
                return "{}"
            return (
                "{ "
                + ", ".join(
                    f"{_format_key(str(k))} = {_format_value(i)}" for k, i in d.items() if i is not None
                )
                + " }"
            )
        case _:
            return _format_string(str(v))


def _to_toml_value(v: Any, field: FieldInfo | None = None) -> Any:
    """Convert python value to json compatible value

    Use the field's type serializer if available, so that custom
    serializers (enums, import strings, templates...) are honored.
    Since default values may not be validated (i.e default given
    in input form), the value is validated before serialization
    if direct serialization fails.

    Fallback to pydantic generic conversion, then to `str`.
    """
    if field is not None and field.annotation is not None:
        annotation: Any = field.annotation
        if field.metadata:
            annotation = Annotated[(annotation, *field.metadata)]
        adapter: TypeAdapter[Any] = TypeAdapter(annotation)
        # Note: default may be not validated
        for convert in (lambda: v, lambda: adapter.validate_python(v)):
            try:
                return adapter.dump_python(convert(), mode="json", warnings=False)
            except Exception:  # noqa: S112
                continue
    try:
        return to_jsonable_python(v)
    except Exception:
        return str(v)


#
# Defaults
#


def _field_default(field: FieldInfo) -> Any:
    """Return the default value or PydanticUndefined

    Default factories are called; PydanticUndefined is returned
    for required fields or if the factory fails.
    """
    if field.default is not PydanticUndefined:
        return field.default
    if field.default_factory is not None:
        try:
            return field.get_default(call_default_factory=True, validated_data={})
        except Exception:
            return PydanticUndefined
    return PydanticUndefined


def _get_default(parent: Any, name: str, field: FieldInfo) -> Any:
    """Get the default value of a field from the parent
    default value if any or the field default.

    The parent default may be a model instance or a mapping:
    this allows default values set at the section level (i.e
    `Field(default=MyModel(foo=...))`) to override field defaults.
    """
    if isinstance(parent, BaseModel):
        return getattr(parent, name, PydanticUndefined)
    if isinstance(parent, Mapping) and name in parent:
        return parent[name]
    return _field_default(field)


#
# Output
#


class _Writer:
    """Write TOML lines and comments to a stream"""

    def __init__(self, s: IO):
        self._s = s

    def line(self, text: str = "", comment: bool = False):
        """Write a line, commented out if `comment` is True"""
        print(f"#{text}" if comment else text, file=self._s)

    def doc(self, text: str):
        """Write a (multiline) text as comment lines"""
        for line in dedent(text.strip("\n")).split("\n"):
            self.line(f"# {line}".rstrip() if line else "#")

    def field_doc(self, field: FieldInfo):
        """Write the field's title, description and examples
        as comments
        """
        if field.title:
            self.line("#")
            self.line(f"# {field.title}")
        if field.description:
            self.line("#")
            for line in field.description.split("\n"):
                self.line(f"# {line}")
        for example in field.examples or ():
            self.line("#")
            self.line("# Example:")
            self.line("#")
            example = example if isinstance(example, str) else _format_value(_to_toml_value(example))
            for line in dedent(example).removeprefix("\n").split("\n"):
                self.line(f"# {line}")

    def model_doc(self, model: type[BaseModel]):
        """Write the model's docstring as comments

        Inherited docstrings are not output.
        """
        doc = model.__dict__.get("__doc__")
        if doc:
            self.doc(inspect.cleandoc(doc))


def _field_name(name: str, field: FieldInfo) -> str:
    """Return the TOML key for a field

    Use the alias if defined since this is the name
    expected for validation.
    """
    return _format_key(field.alias or name)


def _iter_fields(model: type[BaseModel]) -> Iterator[tuple[str, FieldInfo]]:
    """Iterate over the documentable fields of a model

    Excluded fields and fields without annotation are skipped.
    """
    for name, field in model.model_fields.items():
        if field.exclude or field.annotation is None:
            continue
        yield name, field


def _write_value(
    w: _Writer,
    key: str,
    field: FieldInfo,
    default: Any,
    comment: bool,
):
    """Write a plain value field with its documentation

    Required fields and fields with a `None` default are always
    commented out since there is no value to output.
    """
    w.field_doc(field)
    if default is PydanticUndefined:
        w.line(f"#{key} =   \t# Required")
    elif default is None:
        w.line(f"#{key} =   \t# Optional")
    else:
        w.line(f"{key} = {_format_value(_to_toml_value(default, field))}", comment)


@dataclass
class _Section:
    """A TOML section (table) to output

    * path: list of formatted keys of the section header
    * model: the model describing the section's content
    * default: the section default value (model instance, mapping
      or PydanticUndefined) used for getting field defaults
    * field: the parent field the section is defined from (None for root)
    * is_array: output as an array of tables (`[[...]]`)
    * comment: comment out the whole section
    * depth: nesting depth, 0 for the root model
    """

    path: list[str]
    model: type[BaseModel]
    default: Any
    field: FieldInfo | None = None
    is_array: bool = False
    comment: bool = False
    depth: int = 0


def _pick_model(models: list[type[BaseModel]], value: Any) -> type[BaseModel] | None:
    """Select the model matching a default value

    Return the model the value is an instance of, or the single
    candidate model if there is no ambiguity, None otherwise.
    """
    for m in models:
        if isinstance(value, m):
            return m
    return models[0] if len(models) == 1 else None


def _sub_sections(
    path: list[str],
    name: str,
    field: FieldInfo,
    default: Any,
    comment: bool,
    depth: int,
) -> list[_Section] | None:
    """Return the sections for the field or None
    if the field is not a section

    When the default holds actual values (model instance, non-empty
    list or dict) sections are output from these values, otherwise
    a template section is output for each candidate model.
    """
    kind = _field_kind(field.annotation)
    key = _field_name(name, field)

    def section(path, model, default, *, is_array=False, comment=comment):
        """Create a child section of the field"""
        return _Section(path, model, default, field, is_array, comment, depth + 1)

    match kind.kind:
        case "model":
            if default is not None and default is not PydanticUndefined:
                m = _pick_model(kind.models, default)
                if m:
                    return [section([*path, key], m, default)]
            # Comment out section if not set by default, alternatives
            # are always commented out
            return [
                section(
                    [*path, key],
                    m,
                    PydanticUndefined,
                    comment=comment or default is None or i > 0,
                )
                for i, m in enumerate(kind.models)
            ]
        case "list":
            if isinstance(default, (list, tuple)) and default:
                items = [(_pick_model(kind.models, v), v) for v in default]
                if all(m for m, _ in items):
                    return [section([*path, key], m, v, is_array=True) for m, v in items]
            return [section([*path, key], m, PydanticUndefined, is_array=True) for m in kind.models]
        case "dict":
            if isinstance(default, Mapping) and default:
                entries = [(k, _pick_model(kind.models, v), v) for k, v in default.items()]
                if all(m for _, m, _ in entries):
                    return [section([*path, key, _format_key(str(k))], m, v) for k, m, v in entries]
            return [
                section([*path, key, f"'key{i if len(kind.models) > 1 else ''}'"], m, PydanticUndefined)
                for i, m in enumerate(kind.models)
            ]
        case _:
            return None


def _write_section(w: _Writer, section: _Section):
    """Write a section and, recursively, its sub-sections

    The header and documentation are written first (except for the
    root section), then the plain value fields; sub-sections are
    deferred after all values since TOML requires that
    keys of a table are defined before any sub-table.
    """
    model = section.model
    comment = section.comment
    path = section.path

    if path:
        w.line()
        if section.depth <= 1:
            w.line()
        if section.field:
            w.field_doc(section.field)
            if section.depth > 1:
                w.line("#")
        w.model_doc(model)
        header = ".".join(path)
        w.line(f"[[{header}]]" if section.is_array else f"[{header}]", comment)

    deferred: list[_Section] = []
    for name, field in _iter_fields(model):
        default = _get_default(section.default, name, field)
        subs = _sub_sections(path, name, field, default, comment, section.depth)
        if subs is not None:
            deferred.extend(subs)
        else:
            _write_value(w, _field_name(name, field), field, default, comment)

    for sub in deferred:
        _write_section(w, sub)


def dump_model_toml(s: IO, model: type[BaseModel]):
    """Dump base model and all its definitions

    Output a documented TOML configuration with default values
    from the model, the root model fields are top level keys or sections.
    """
    _write_section(_Writer(s), _Section([], model, PydanticUndefined))
