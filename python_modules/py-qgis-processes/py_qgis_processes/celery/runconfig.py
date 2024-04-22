import inspect

from textwrap import dedent

from pydantic import (
    BaseModel,
    Field,
    JsonValue,
    TypeAdapter,
    create_model,
    fields,
)
from typing_extensions import (
    Callable,
    Dict,
    Optional,
    Tuple,
    Type,
)

# from as_core.storage import StorageClient, StorageCreds, storage_client

# Worker task configuration
#


class RunConfig(BaseModel, frozen=True, extra='ignore'):
    """Base config model for tasks
    """
    pass


#
# Run configs
#

class InputDescription(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    schema_: JsonValue = Field(alias="schema")


class OutputDescription(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    schema_: JsonValue = Field(alias="schema")


class RunConfigSchema(BaseModel):
    title: str
    description: Optional[str] = None
    inputs: Dict[str, InputDescription]
    outputs: Dict[str, OutputDescription]


def _format_doc(wrapped: Callable) -> Tuple[str, str]:
    # Get title and description from docstring
    if wrapped.__doc__:
        doc = dedent(wrapped.__doc__)
        title, *rest = doc.strip("\n ").split('\n', maxsplit=1)
        description = rest[0].strip("\n") if rest else ""
    else:
        title = wrapped.__qualname__
        description = ""

    return title, description


def _fix_annotation_ellipsis(anno, default):
    # Workaround https://github.com/pydantic/pydantic/issues/8634
    # :split annotaion and Field and use field as default value
    if default ==  ...:
        if anno.__name__ == 'Annotated':
            field, *_ = anno.__metadata__
            if isinstance(field, fields.FieldInfo):
                anno = anno.__args__[0]
                default = field

    return (anno, default)


def create_job_run_config(
    wrapped: Callable,
) -> Tuple[Tuple[Type[RunConfig], TypeAdapter], RunConfigSchema]:
    """ Build a RunConfig from fonction signature
    """
    s = inspect.signature(wrapped)
    qualname = wrapped.__qualname__

    title, description = _format_doc(wrapped)

    def _models():
        for p in s.parameters.values():
            match p.kind:
                case p.POSITIONAL_ONLY | p.VAR_POSITIONAL | p.VAR_KEYWORD:
                    continue
                case p.POSITIONAL_OR_KEYWORD | p.KEYWORD_ONLY:
                    has_default = p.default is not inspect.Signature.empty
                    if p.annotation is inspect.Signature.empty:
                        raise TypeError(
                            "Missing annotation for argument "
                            f"{p.name} in job {qualname}",
                        )
                    yield p.name, (
                        p.annotation,
                        p.default if has_default else ...,
                    )

    _inputs = {name: model for name, model in _models()}

    # Inputs
    inputs = create_model(
        "_RunConfig",
        __base__=RunConfig,
        **dict((n, _fix_annotation_ellipsis(a, d)) for n, (a, d) in _inputs.items()),
    )

    # Build schema for each properties
    def input_schemas():
        for name, (a, d) in _inputs.items():
            s = TypeAdapter(a).json_schema()
            if d != ...:
                s['default'] = d
            yield name, InputDescription(
                title=s.pop('title', None),
                description=s.pop('description', None),
                schema=s,
            )

    # Outputs
    if s.return_annotation is not inspect.Signature.empty:
        return_annotation = s.return_annotation
    else:
        return_annotation = None

    outputs = TypeAdapter(return_annotation or JsonValue)
    output_schema = outputs.json_schema()

    return (inputs, outputs), RunConfigSchema(
        title=title,
        description=description,
        inputs=dict(input_schemas()),
        outputs={'return': OutputDescription(
                title=output_schema.pop('title', "Return"),
                schema=output_schema,
            ),
        } if return_annotation else {},
    )
