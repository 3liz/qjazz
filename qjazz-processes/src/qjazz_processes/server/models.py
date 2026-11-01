from enum import StrEnum
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
    ValidationError,
)
from qjazz_core.models import Field, Option

from ..schemas import ServiceName
from .swagger import JsonModel, model

OGC_EXCEPTION_URI = "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0"


class ExceptionType(StrEnum):
    """OGC API - Processes exception types"""

    NoSuchProcess = f"{OGC_EXCEPTION_URI}/no-such-process"
    NoSuchJob = f"{OGC_EXCEPTION_URI}/no-such-job"
    ResultNotReady = f"{OGC_EXCEPTION_URI}/result-not-ready"


# Default type for exceptions with no specific
# type (see RFC 7807)
DEFAULT_EXCEPTION_TYPE = "about:blank"


@model
class ErrorResponse(JsonModel):
    """Error response

    Compatible with the OGC API exception schema (RFC 7807)
    """

    type_: str = Field(
        default=DEFAULT_EXCEPTION_TYPE,
        alias="type",
        title="Exception type",
    )
    status: Option[int] = None
    message: str
    details: Option[JsonValue] = None

    @classmethod
    def raises(
        cls,
        error_type: Type[web.HTTPException],
        message: str,
        details: Option[JsonValue] = None,
        *,
        exception: Optional[ExceptionType] = None,
    ) -> NoReturn:
        raise error_type(
            content_type="application/json",
            text=cls(
                type_=exception or DEFAULT_EXCEPTION_TYPE,
                status=error_type.status_code,
                message=message,
                details=details,
            ).model_dump_json(),
        ) from None

    @classmethod
    def response(
        cls,
        status: int,
        message: str,
        details: Option[JsonValue] = None,
        *,
        exception: Optional[ExceptionType] = None,
    ) -> web.Response:
        return web.Response(
            status=status,
            content_type="application/json",
            text=cls(
                type_=exception or DEFAULT_EXCEPTION_TYPE,
                status=status,
                message=message,
                details=details,
            ).model_dump_json(),
        )


RequestHandler = Callable[[web.Request], Awaitable[web.StreamResponse]]

# Validators
BoolParam: TypeAdapter[bool] = TypeAdapter(bool)
ServiceNameParam: TypeAdapter[str] = TypeAdapter(ServiceName)


def validate_service_name(service: str) -> str:
    """Validate a service name from request parameters

    The service name is used in registry key patterns
    """
    try:
        return ServiceNameParam.validate_python(service)
    except ValidationError:
        ErrorResponse.raises(
            web.HTTPBadRequest,
            "Invalid service name",
            details={"service": service},
        )
