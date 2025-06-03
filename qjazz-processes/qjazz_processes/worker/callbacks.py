#
# Handle callbacks
# See https://docs.ogc.org/is/18-062r2/18-062r2.html#toc52 for
# OGC specifications
import traceback

from contextlib import contextmanager
from typing import (
    Annotated,
    Optional,
    Protocol,
    Self,
    cast,
    runtime_checkable,
)
from urllib.parse import SplitResult as Url
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    BeforeValidator,
    ImportString,
    JsonValue,
    TypeAdapter,
    WithJsonSchema,
    model_validator,
)

from qjazz_contrib.core import logger
from qjazz_contrib.core.config import ConfigBase
from qjazz_contrib.core.models import Field

from ..schemas import JobResults


@runtime_checkable
class CallbackHandler(Protocol):
    def on_success(self, url: Url, job_id: str, results: JobResults): ...

    def on_failure(self, url: Url, job_id: str): ...

    def in_progress(self, url: Url, job_id: str): ...


def _parse_config_options(val: str | dict[str, JsonValue]) -> dict[str, JsonValue]:
    if isinstance(val, str):
        val = TypeAdapter(dict[str, JsonValue]).validate_json(val)
    return val


HandlerConfigOptions = Annotated[
    dict[str, JsonValue],
    BeforeValidator(_parse_config_options),
]


class HandlerConfig(ConfigBase):
    handler: Annotated[
        ImportString,
        WithJsonSchema({"type": "string}"}),
        Field(validate_default=True, title="Callback module", description="The callback handler import string"),
    ]
    config: HandlerConfigOptions = Field(
        default={},
        title="Callback configuration",
    )

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        klass = self.handler

        if not issubclass(klass, CallbackHandler):
            raise ValueError(f"{klass} does not support CallbackHandler protocol")

        self._handler_conf: BaseModel | None = None
        if hasattr(klass, "Config") and issubclass(klass.Config, BaseModel):
            self._handler_conf = klass.Config.model_validate(self.config)

        return self

    def create_instance(self, scheme: str) -> CallbackHandler:
        logger.info(
            "Creating '%s' callback handler for scheme '%s'",
            self.handler,
            scheme,
        )

        if self._handler_conf:
            return self.handler(self._handler_conf)
        else:
            return self.handler()


#
# Callbacks config
#

CallbacksConfig = Annotated[
    dict[str, HandlerConfig],
    Field(
        description="""
        Callbacks configuration.
        Define a mapping between protocol and handler.
        """,
        examples=[
            "{ 'https': 'qjazz_processes.callbacks.HttpCallback' }",
        ],
    ),
]


@contextmanager
def infallible(uri: str):
    try:
        yield
    except Exception:
        logger.error("Callback '%s' failed:\n%s", uri, traceback.format_exc())


class Callbacks:
    def __init__(self, conf: CallbacksConfig):
        self._handlers = {k: cnf.create_instance(k) for k, cnf in conf.items()}

    def get_handler_for(self, uri: str) -> Optional[tuple[Url, CallbackHandler]]:
        url = urlsplit(uri)
        handler = self._handlers.get(url.scheme)
        if handler:
            return (url, cast(CallbackHandler, handler))
        else:
            logger.warning("No callback handler found for %s", uri)
            return None

    def on_success(self, uri: str, job_id: str, results: JobResults):
        rv = self.get_handler_for(uri)
        if rv:
            url, handler = rv
            with infallible(uri):
                handler.on_success(url, job_id, results)

    def on_failure(self, uri: str, job_id: str):
        rv = self.get_handler_for(uri)
        if rv:
            url, handler = rv
            with infallible(uri):
                handler.on_failure(url, job_id)

    def in_progress(self, uri: str, job_id: str):
        rv = self.get_handler_for(uri)
        if rv:
            url, handler = rv
            with infallible(uri):
                handler.in_progress(url, job_id)
