"""Load and register protocol handler from
external modules.

Allow for third party to define custom
storage handlers
"""

import urllib.parse

from typing import (
    Annotated,
    Any,
    Protocol,
    Self,
    runtime_checkable,
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

Url = urllib.parse.SplitResult


def _parse_config_options(val: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(val, str):
        val = TypeAdapter(dict[str, Any]).validate_json(val)
    return val


@runtime_checkable
class StorageHandler(Protocol):
    def resolve_uri(self, url: Url) -> str:
        """Sanitize uri for using as catalog key entry

        The returned uri must ensure unicity of the
        resource location

        Must be idempotent
        """
        raise NotImplementedError

    def public_path(self, uri: str | Url, location: str, rooturl: Url) -> str:
        """Given a search path and an uri corressponding to
        a resolved_uri for this handler, it returns the uri
        usable relative to the search path.
        """
        raise NotImplementedError


HandlerConfigOptions = Annotated[
    dict[str, Any],
    BeforeValidator(_parse_config_options),
]


class StorageHandlerConfig(ConfigBase):
    handler: Annotated[
        ImportString,
        WithJsonSchema({"type": "string"}),
        Field(validate_default=True),
    ]
    config: HandlerConfigOptions = Field({})

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        klass = self.handler

        if not issubclass(klass, StorageHandler):
            raise TypeError(f"{klass} does not suppport ResourceStoreprotocol")

        self._handler_conf: BaseModel | None = None
        if hasattr(klass, "Config") and issubclass(klass.Config, BaseModel):
            self._handler_conf = klass.Config.model_validate(self.config)

        return self

    def create_instance(self) -> StorageHandler:
        if self._handler_conf:
            return self.handler(self._handler_conf)
        return self.handler()


def register_storage_handler(scheme: str, conf: StorageHandlerConfig):
    """Import and initialize storage handler"""
    logger.info("Cache: Initalizing storage handler [%s]: %s", scheme, str(conf.handler))

    # Register instance as a service
    componentmanager.gComponentManager.register_service(
        f"@3liz.org/cache/storage-handler;1?scheme={scheme}",
        conf.create_instance(),
    )
