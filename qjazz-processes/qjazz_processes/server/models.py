from typing import (
    Awaitable,
    Callable,
    NoReturn,
    Optional,
    Type,
)

from aiohttp import web
from pydantic import (
    JsonValue,
    TypeAdapter,
)

from .swagger import JsonModel, model


@model
class ErrorResponse(JsonModel):
    message: str
    details: Optional[JsonValue] = None

    @classmethod
    def raises(
        cls,
        error_type: Type[web.HTTPException],
        message: str,
        details: Optional[JsonValue] = None,
    ) -> NoReturn:
        raise error_type(
            content_type="application/json",
            text=cls(
                message=message,
                details=details,
            ).model_dump_json(),
        ) from None

    @classmethod
    def response(
        cls,
        status: int,
        message: str,
        details: Optional[JsonValue] = None,
    ) -> web.Response:
        return web.Response(
            status=status,
            content_type="application/json",
            text=ErrorResponse(
                message=message,
                details=details,
            ).model_dump_json(),
        )

RequestHandler = Callable[[web.Request], Awaitable[web.StreamResponse]]

# Validators
BoolParam: TypeAdapter[bool] = TypeAdapter(bool)
