import inspect
import sys  # noqa

from pydantic import BaseModel, Field
from typing_extensions import IO, Type

#
# Output valid TOML default configuration
#


def _print_field_doc(s: IO, field: Field):
    if field.title:
        print('#', file=s)
        print(f"# {field.title}", file=s)
    if field.description:
        print('#', file=s)
        for line in field.description.split('\n'):
            print(f"# {line}", file=s)


def _field_default_repr(field: Field) -> str:
    match field.default:
        case str(s):
            return f'"{s}"'
        case bool(b):
            return "true" if b else "false"
        case int(n) | float(n):
            return f'{n}'
        case tuple(t):
            return list(t)
        case default:
            if field.is_required():
                return "\t# Required"
            else:
                return default


def _print_field(s: IO, name: str, field: Field, comment: bool = False):
    if field.default is None:
        # Optional field
        print(f"#{name} =   \t# Optional", file=s)
    elif comment:
        print(f"#{name} = {_field_default_repr(field)}", file=s)
    else:
        print(f"{name} = {_field_default_repr(field)}", file=s)


def _print_model_doc(s: IO, model: Type[BaseModel]):
    if model.__doc__:
        doc = model.__doc__.strip('\n')
        for line in doc.split('\n'):
            print(f"# {line}", file=s)


def _dump_model(s: IO, model: Type[BaseModel], section: str, comment: bool = False):
    """ Dump model as properties
    """
    _print_model_doc(s, model)
    if comment:
        print(f"#{section}")
    else:
        print(section)

    for name, field in model.model_fields.items():
        _print_field_doc(s, field)
        _print_field(s, name, field, comment=comment)


def _is_model(t: Type) -> bool:
    return inspect.isclass(t) and issubclass(t, BaseModel)


def _unpack_arg(t: Type) -> Type:
    match t.__name__:
        case 'Annotated':
            return _unpack_arg(t.__args__[0])
        case 'Optional':
            return _unpack_arg(t.__args__[0])
        case _:
            return t


def _dump_section(s: IO, model: Type[BaseModel], section: str, comment: bool = False):
    """ Dump a model as a toml
    """
    _deferred = []

    if comment:
        print(f"#[{section}]", file=s)
    else:
        print(f"[{section}]", file=s)

    def defer(name, field, arg) -> bool:
        arg = _unpack_arg(arg)
        rv = False
        if _is_model(arg):
            _deferred.append((arg, name.format(key="key"), field))
            rv = True
        elif arg.__name__ == 'Union':
            for i, m in enumerate(arg.__args__):
                if _is_model(m):
                    _deferred.append((m, name.format(key=f"key{i}"), field))
                    rv = True
        return rv

    for name, field in model.model_fields.items():
        a = field.annotation
        match a.__name__:
            case 'List' | 'Tuple' | 'Union':
                deferred = defer(f"[[{section}.{name}]]", field, a.__args__[0])
            case 'Dict':
                deferred = defer(f"[{section}.{name}.{{key}}]", a.__args__[1])
            case 'Union':
                deferred = defer(f"[{section}.{name}]", field, a.__args__[0])
            case _:
                deferred = defer(f"[{section}.{name}]", field, a)

        if not deferred:
            _print_field_doc(s, field)
            _print_field(s, name, field, comment=comment)
        else:
            _print_field_doc(s, field)
            _print_field(s, name, field, comment=True)

    for model, name, field in _deferred:
        print(file=s)
        _print_field_doc(s, field)
        print("#", file=s)
        _dump_model(s, model, name, comment=comment or not field.is_required())


def dump_model_toml(s: IO, model: Type[BaseModel]):
    """ Dump base model and all its definitions
    """
    print(file=s)
    for name, field in model.model_fields.items():
        _print_field_doc(s, field)
        a = _unpack_arg(field.annotation)
        if _is_model(a):
            _print_model_doc(s, a)
            _dump_section(s, a, name, comment=field.annotation.__name__ == 'Optional')
        elif a.__name__ == 'List':
            arg = a.__args__[0]
            # Only print base model arguments
            if _is_model(arg):
                _dump_model(s, arg, f"[[{name}]]", comment=True)
            elif arg.__name__ == 'Union':
                for m in arg.__args__:
                    assert _is_model(m)
                    print(file=s)
                    _dump_model(s, m, f"[[{name}]]", comment=True)
        elif a.__name__ == 'Dict':
            arg = a.__args__[1]
            # Only print base model arguments
            if _is_model(arg):
                _print_model_doc(s, arg)
                _dump_section(s, arg, f"{name}.key", comment=True)
            elif arg.__name__ == 'Union':
                for i, m in enumerate(arg.__args__):
                    assert _is_model(m)
                    print(file=s)
                    _dump_section(s, m, f"{name}.key{i}", comment=True)
        else:
            _print_field_doc(s, field)
            _print_field(s, name, field, comment=True)
        print(file=s)
