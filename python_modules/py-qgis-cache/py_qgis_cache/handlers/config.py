""" Load and register protocol handler from
    external modules.

    Allow for third party to define custom
    protocel handlers
"""

from pydantic import (
    BaseModel,
    Field,
    ImportString,
    JsonValue,
    WithJsonSchema,
    model_validator,
)
from typing_extensions import (
    Annotated,
    Dict,
    Self,
)

from py_qgis_contrib.core import componentmanager, logger
from py_qgis_contrib.core.config import ConfigBase

from ..common import ProtocolHandler


class HandlerConfig(ConfigBase):
    handler_class: Annotated[
        ImportString,
        WithJsonSchema({'type': 'string'}),
        Field(validate_default=True),
    ]
    config: Dict[str, JsonValue] = Field({})

    @model_validator(mode='after')
    def validate_config(self) -> Self:

        klass = self.handler_class

        if not issubclass(klass, ProtocolHandler):
            raise ValueError(f"{klass} does not suppport ProtocolHandler protocol")

        self._handler_conf: BaseModel | None = None
        if hasattr(klass, 'Config') and issubclass(klass.Config, BaseModel):
            self._handler_conf = klass.Config.model_validate(self.config)

        return self

    def create_instance(self) -> ProtocolHandler:
        if self._handler_conf:
            return self.handler_class(self._handler_conf)
        else:
            return self.handler_class()


def register_protocol_handler(scheme: str, conf: HandlerConfig):
    """ Import and initialize protocol handler
    """
    logger.info("Cache: Initalizing protocol handler [%s]: %s", scheme, str(conf.handler_class))

    # Register instance as a service
    componentmanager.gComponentManager.register_service(
        f'@3liz.org/cache/protocol-handler;1?scheme={scheme}',
        conf.create_instance(),
    )
