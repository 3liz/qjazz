#
# Handle callbacks
# See https://docs.ogc.org/is/18-062r2/18-062r2.html#toc52 for
# OGC specifications
#
import traceback

from contextlib import contextmanager
from typing import (
    Annotated,
    Iterable,
    Iterator,
    Optional,
    Protocol,
    Self,
    Sequence,
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
from ..worker.models import JobMeta


@runtime_checkable
class CallbackHandler(Protocol):
    def on_success(self, url: Url, job_id: str, meta: JobMeta, results: JobResults): ...

    def on_failure(self, url: Url, job_id: str, meta: JobMeta): ...

    def in_progress(self, url: Url, job_id: str, meta: JobMeta): ...


def _parse_config_options(val: str | dict[str, JsonValue]) -> dict[str, JsonValue]:
    if isinstance(val, str):
        val = TypeAdapter(dict[str, JsonValue]).validate_json(val)
    return val


HandlerConfigOptions = Annotated[
    dict[str, JsonValue],
    BeforeValidator(_parse_config_options),
]


# For syntactic sugar in config file
_handler_aliases = {
    "qjazz_processes.callbacks.Test": "qjazz_processes.callbacks.handlers.test.TestCallback",
    "qjazz_processes.callbacks.Http": "qjazz_processes.callbacks.handlers.http.HttpCallback",
    "qjazz_processes.callbacks.MailTo": "qjazz_processes.callbacks.handlers.mailto.MailToCallback",
}


class HandlerConfig(ConfigBase):
    enabled: bool = Field(True, title="Enable callback")
    handler: Annotated[
        ImportString,
        BeforeValidator(lambda s: _handler_aliases.get(s, s)),
        WithJsonSchema({"type": "string"}),
        Field(
            validate_default=True,
            title="Callback module",
            description="The callback handler import string",
        ),
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

    def create_instance(self, schemes: Sequence[str]) -> CallbackHandler:
        if self._handler_conf:
            return self.handler(schemes, self._handler_conf)
        else:
            return self.handler(schemes)


#
# Callbacks config
#

CallbacksConfig = Annotated[
    dict[str, HandlerConfig],
    Field(
        title="Callbacks",
        description="""
        Define a mapping between a uri scheme and a handler for that
        scheme.
        """,
        examples=[
            """
            [callbacks.https]
            handler = "qjazz_processes.callbacks.Http",
            """,
        ],
    ),
]


class Callbacks:
    def __init__(self, conf: CallbacksConfig):
        def _instances() -> Iterator[tuple[str, CallbackHandler]]:
            for k, cnf in conf.items():
                if not cnf.enabled:
                    continue

                schemes = tuple(s.strip() for s in k.split(","))
                logger.info(
                    "Creating '%s' callback handler for schemes '%s'",
                    cnf.handler,
                    schemes,
                )
                inst = cnf.create_instance(schemes)
                for scheme in schemes:
                    yield scheme, inst

        self._handlers = dict(_instances())

    @property
    def schemes(self) -> Iterable[str]:
        return self._handlers.keys()

    def get_handler_for(self, uri: str) -> Optional[tuple[Url, CallbackHandler]]:
        url = urlsplit(uri)
        handler = self._handlers.get(url.scheme)
        if handler:
            return (url, cast(CallbackHandler, handler))
        else:
            logger.warning("No callback handler found for %s", uri)
            return None

    def on_success(self, uri: str, job_id: str, meta: JobMeta, results: JobResults):
        rv = self.get_handler_for(uri)
        if rv:
            url, handler = rv
            with infaillible(uri):
                handler.on_success(url, job_id, meta, results)

    def on_failure(self, uri: str, job_id: str, meta: JobMeta):
        rv = self.get_handler_for(uri)
        if rv:
            url, handler = rv
            with infaillible(uri):
                handler.on_failure(url, job_id, meta)

    def in_progress(self, uri: str, job_id: str, meta: JobMeta):
        rv = self.get_handler_for(uri)
        if rv:
            url, handler = rv
            with infaillible(uri):
                handler.in_progress(url, job_id, meta)


@contextmanager
def infaillible(uri):
    try:
        yield
    except Exception:
        logger.error("Callback failed for '%s':\n%s", uri, traceback.format_exc())
