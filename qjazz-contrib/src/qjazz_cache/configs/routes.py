
from typing import Annotated, cast

from pydantic import (
    PlainSerializer,
    PlainValidator,
    TypeAdapter,
    WithJsonSchema,
)

from ..routes import Routes

Bool = TypeAdapter(bool)


def validate_routes(v: str | dict[str, str]) -> Routes:
    match v:
        case str():
            v = TypeAdapter(dict[str, str]).validate_json(v)
        case dict():
            pass
        case _:
            raise ValueError("Mapping or json string expected")
    return Routes(cast("dict", v))


RoutesDef = Annotated[
    Routes,
    PlainValidator(validate_routes),
    PlainSerializer(
        lambda routes: {k: v.geturl() for k, v in routes.cannonical},
        return_type=dict[str, str],
    ),
    WithJsonSchema(TypeAdapter(dict[str, str]).json_schema()),
]


