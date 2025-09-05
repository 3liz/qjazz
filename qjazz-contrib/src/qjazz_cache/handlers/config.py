"""Load and register protocol handler from
external modules.

Allow for third party to define custom
protocel handlers
"""

from typing import (
    Annotated,
    Any,
    Self,
)

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    ImportString,
    TypeAdapter,
    WithJsonSchema,
    model_validator,
)

from qjazz_core import componentmanager, logger
from qjazz_core.config import ConfigBase

from ..common import ProtocolHandler


def _parse_config_options(val: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(val, str):
        val = TypeAdapter(dict[str, Any]).validate_json(val)
    return val


HandlerConfigOptions = Annotated[
    dict[str, Any],
    BeforeValidator(_parse_config_options),
]


class HandlerConfig(ConfigBase):
    handler: Annotated[
        ImportString,
        WithJsonSchema({"type": "string"}),
        Field(validate_default=True),
    ]
    config: HandlerConfigOptions = Field({})

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        klass = self.handler

        if not issubclass(klass, ProtocolHandler):
            raise ValueError(f"{klass} does not suppport ProtocolHandler protocol")

        self._handler_conf: BaseModel | None = None
        if hasattr(klass, "Config") and issubclass(klass.Config, BaseModel):
            self._handler_conf = klass.Config.model_validate(self.config)

        return self

    def create_instance(self) -> ProtocolHandler:
        if self._handler_conf:
            return self.handler(self._handler_conf)
        else:
            return self.handler()


def register_protocol_handler(scheme: str, conf: HandlerConfig):
    """Import and initialize protocol handler"""
    logger.info("Cache: Initalizing protocol handler [%s]: %s", scheme, str(conf.handler))

    # Register instance as a service
    componentmanager.gComponentManager.register_service(
        f"@3liz.org/cache/protocol-handler;1?scheme={scheme}",
        conf.create_instance(),
    )
