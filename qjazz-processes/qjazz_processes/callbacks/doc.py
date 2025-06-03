import sys

from typing import Literal, Type

from qjazz_contrib.core.config import ConfBuilder, ConfigBase
from qjazz_contrib.core.models import Field


def dump_callback_config_schema(name: str, CallbackConfigType: Type) -> None:
    """Dump schema as toml configuration"""

    class CallbackConfig(ConfigBase):
        enabled: bool = Field(True, title="Enable callback")
        handler: Literal[(name,)] = Field(name)  # type: ignore [valid-type]
        config: CallbackConfigType = Field(CallbackConfigType())  # type: ignore [valid-type]

    class ConfigModel(ConfigBase):
        http: CallbackConfig = Field(CallbackConfig())

    confservice = ConfBuilder(with_global_sections=False)
    confservice.add_section("callbacks", ConfigModel)
    confservice.dump_toml_schema(sys.stdout)
