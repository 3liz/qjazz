
from collections.abc import Callable

from pydantic import TypeAdapter
from pydantic.config import JsonDict
from typing_extensions import (
    Any,
    Dict,
    Optional,
    TypeAlias,
)

from py_qgis_processes.schemas import (
    InputDescription,
    ValuePassing,
    remove_auto_title,
)
from py_qgis_processes.schemas.models import one_of


def model_description(
    annotated: TypeAlias,
    *,
    title: Optional[str],
    description: Optional[str],
    optional: bool = False,
    value_passing: Optional[ValuePassing] = None,
    schema_extra: Optional[JsonDict | Callable[[JsonDict], None]] = None,
) -> InputDescription:
    """ Return model as InputDescription
    """
    schema = TypeAdapter(annotated).json_schema(by_alias=True)

    kwargs: Dict[str, Any] = {}
    if optional:
        kwargs.update(min_occurs=0)

    match schema_extra:
        case dict():
            schema.update(schema_extra)
        case Callable():  # type: ignore [misc]
            schema_extra(schema)

    schema.pop('title', None)
    one_of(schema)
    remove_auto_title(schema)

    return InputDescription(
        title=title,
        description=description,
        schema=schema,
        value_passing=value_passing or ('byValue',),
        ** kwargs,
    )
