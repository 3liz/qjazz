from collections.abc import Callable
from typing import (
    Any,
    Optional,
    TypeAlias,
)

from pydantic import TypeAdapter
from pydantic.config import JsonDict

from .models import one_of, remove_auto_title
from .processes import (
    InputDescription,
    MetadataValue,
    ProcessSummary,
    ValuePassing,
)


def input_model_description(
    annotated: TypeAlias,
    *,
    title: Optional[str],
    description: Optional[str],
    optional: bool = False,
    value_passing: Optional[ValuePassing] = None,
    schema_extra: Optional[JsonDict | Callable[[JsonDict], None]] = None,
) -> InputDescription:
    """Return model as InputDescription"""
    schema = TypeAdapter(annotated).json_schema(by_alias=True)

    kwargs: dict[str, Any] = {}
    if optional:
        kwargs.update(min_occurs=0)

    match schema_extra:
        case dict():
            schema.update(schema_extra)
        case Callable():  # type: ignore [misc]
            schema_extra(schema)

    schema.pop("title", None)
    one_of(schema)
    remove_auto_title(schema)

    return InputDescription(
        title=title,
        description=description,
        schema=schema,
        value_passing=value_passing or ("byValue",),
        **kwargs,
    )


def get_annotation(role: str, process: ProcessSummary) -> bool:
    """Get boolean metadata value"""
    for md in process.metadata:
        if isinstance(md, MetadataValue) and md.role == role:
            return bool(md.value)
    else:
        return False
