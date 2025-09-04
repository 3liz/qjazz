import sys

from typing import Literal, Type

from qjazz_contrib.core.config import ConfBuilder, ConfigBase
from qjazz_contrib.core.models import Field


def dump_callback_config_schema(scheme: str, name: str, CallbackConfigType: Type) -> None:
    """Dump schema as toml configuration"""
    from pydantic import create_model

    class CallbackConfig(ConfigBase):
        enabled: bool = Field(True, title="Enable callback")
        handler: Literal[(name,)] = Field(name)  # type: ignore [valid-type]
        config: CallbackConfigType  # type: ignore [valid-type]

    model = create_model(  # type: ignore [call-overload]
        "ConfigModel",
        __base__=ConfigBase,
        **{scheme: (CallbackConfig, ...)},
    )

    confservice = ConfBuilder(with_global_sections=False)
    confservice.add_section("callbacks", model, ...)
    confservice.dump_toml_schema(sys.stdout)
