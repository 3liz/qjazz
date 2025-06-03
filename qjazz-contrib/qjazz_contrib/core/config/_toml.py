import inspect
import sys  # noqa

from textwrap import dedent
from types import UnionType
from typing import IO, Type

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from ..condition import assert_precondition

#
# Output valid TOML default configuration from
# pydantic schema
#


def _print_field_doc(s: IO, field: FieldInfo):
    if field.title:
        print("#", file=s)
        print(f"# {field.title}", file=s)
    if field.description:
        print("#", file=s)
        for line in field.description.split("\n"):
            print(f"# {line}", file=s)
    if field.examples:
        for example in field.examples:
           print("#\n# Example:\n#", file=s)
           for line in dedent(example).removeprefix("\n").split("\n"):
               print(f"# {line}", file=s)


def _to_string(v: str | bool | int | float) -> str:
    match v:
        case str(s):
            return f'"{s}"'
        case bool(b):
            return "true" if b else "false"
        case int(n) | float(n):
            return f"{n}"
        case _:
            return f'"{v!s}"'


def _field_default_repr(field: FieldInfo) -> str:
    match field.default:
        case str(s):
            return f'"{s}"'
        case bool(b):
            return "true" if b else "false"
        case int(n) | float(n):
            return f"{n}"
        case tuple(t) | set(t) | list(t):
            return f"[{','.join(_to_string(v) for v in t)}]"
        case dict(t):
            return f"{t}"
        case default:
            return f'"{default}"'


def _print_field(s: IO, name: str, field: FieldInfo, comment: bool = False):
    if field.is_required():
        print(f"#{name} =   \t# Required", file=s)
    elif field.default is None:
        # Optional field
        print(f"#{name} =   \t# Optional", file=s)
    elif comment:
        print(f"#{name} = {_field_default_repr(field)}", file=s)
    else:
        print(f"{name} = {_field_default_repr(field)}", file=s)


def _print_model_doc(s: IO, model: Type[BaseModel]):
    if model.__doc__:
        doc = dedent(model.__doc__.strip("\n"))
        for line in doc.split("\n"):
            print(f"# {line}", file=s)


def _dump_model(s: IO, model: Type[BaseModel], section: str, comment: bool = False):
    """Dump model as properties"""
    _print_model_doc(s, model)
    if comment:
        print(f"#{section}", file=s)
    else:
        print(section, file=s)

    for name, fieldinfo in model.model_fields.items():
        _print_field_doc(s, fieldinfo)
        _print_field(s, name, fieldinfo, comment=comment)


def _is_model(t: Type) -> bool:
    return inspect.isclass(t) and issubclass(t, BaseModel)


def _unpack_arg(t: Type) -> Type:
    if hasattr(t, "__name__"):
        match t.__name__:
            case "Annotated" | "Optional":
                return _unpack_arg(t.__args__[0])
    return t


def _dump_section(
    s: IO,
    model: Type[BaseModel],
    section: str,
    comment: bool = False,
    is_list: bool = False,
):
    """Dump a model as a toml"""
    deferred_ = []

    section_format = f"[{section}]"
    if is_list:
        section_format = f"[{section_format}]"

    if comment:
        print(f"#{section_format}", file=s)
    else:
        print(f"{section_format}", file=s)

    def defer(name, field, arg, as_list=False):
        arg = _unpack_arg(arg)
        rv = False
        if _is_model(arg):
            deferred_.append((arg, name.format(key="'key'"), field, as_list))
            rv = True
        elif isinstance(arg, UnionType) or  arg.__name__ == "Union":
            for i, m in enumerate(arg.__args__):
                if _is_model(m):
                    deferred_.append((m, name.format(key=f"'key{i}'"), field))
                    rv = True
        return rv

    for name, field in model.model_fields.items():
        a = field.annotation
        if a is None:  # hu ? no annotation
            continue
        match a.__name__.lower():
            case "list" | "tuple" | "union" | "sequence":
                deferred = defer(f"{section}.{name}", field, a.__args__[0], as_list=True)
            case "dict":
                deferred = defer(f"{section}.{name}.{{key}}", field, a.__args__[1])
            case _:
                deferred = defer(f"{section}.{name}", field, a)

        if not deferred:
            _print_field_doc(s, field)
            _print_field(s, name, field, comment=comment)
        # else:
        #    _print_field_doc(s, field)
        #    _print_field(s, name, field, comment=True)

    for model, name, field, as_list in deferred_:
        print(file=s)
        _print_field_doc(s, field)
        print("#", file=s)
        _dump_section(s, model, name, comment=comment, is_list=as_list)


def dump_model_toml(s: IO, model: Type[BaseModel]):
    """Dump base model and all its definitions"""
    print(file=s)
    for name, field in model.model_fields.items():
        _print_field_doc(s, field)
        if field.annotation is None:
            continue
        a = _unpack_arg(field.annotation)
        if _is_model(a):
            print()
            _print_model_doc(s, a)
            _dump_section(s, a, name, comment=field.annotation.__name__ == "Optional")
        elif a.__name__ in ("List", "Sequence"):
            arg = a.__args__[0]
            # Only print base model arguments
            if _is_model(arg):
                _dump_model(s, arg, f"[[{name}]]")
            elif arg.__name__ == "Union":
                for m in arg.__args__:
                    assert_precondition(_is_model(m))
                    print(file=s)
                    _dump_model(s, m, f"[[{name}]]")
        elif a.__name__.lower() == "dict":
            arg = a.__args__[1]
            # Only print base model arguments
            if _is_model(arg):
                _print_model_doc(s, arg)
                _dump_section(s, arg, f"{name}.'key'")
            elif arg.__name__ == "Union":
                for i, m in enumerate(arg.__args__):
                    assert_precondition(_is_model(m))
                    print(file=s)
                    _dump_section(s, m, f"{name}.'key{i}'")
        else:
            _print_field_doc(s, field)
            _print_field(s, name, field, comment=True)
        print(file=s)
