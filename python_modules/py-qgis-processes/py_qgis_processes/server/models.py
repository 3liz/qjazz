
from aiohttp import web
from pydantic import (
    JsonValue,
)
from typing_extensions import (
    Awaitable,
    Callable,
    NoReturn,
    Optional,
    Type,
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
        )

    @classmethod
    def response(cls,
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
