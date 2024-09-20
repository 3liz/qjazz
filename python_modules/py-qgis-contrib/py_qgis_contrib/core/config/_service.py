#
# Copyright 2024 3liz
# Author David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

""" Configuration management

Configuration can be done either by using aconfiguration file or with environnement variable.

Except stated otherwise, the rule for environnement variable names is
``CONF_[<SECTION>__, ...]<KEY>``.

Casing does not matter but uppercase have precedence

Values are taken from multiple source according
to the [`pydantic` module](https://docs.pydantic.dev/latest/usage/pydantic_settings/#field-value-priority)

See also https://docs.pydantic.dev/latest/concepts/pydantic_settings

Source searched for configuration values:

1. Argument passed to configuration
2. Environment variables starting with `conf_`
3. Variables loaded from a dotenv (.env)
4. Variables loaded from the Docker secrets directory (/run/secrets)
5. The default field values

"""
import os
import sys

from importlib import metadata
from pathlib import Path
from time import time

from pydantic import (
    BaseModel,
    JsonValue,
    TypeAdapter,
    ValidationError,
    create_model,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from typing_extensions import (
    IO,
    Any,
    Callable,
    ClassVar,
    Dict,
    Generic,
    Optional,
    Tuple,
    Type,
    TypeAlias,
    TypeVar,
    assert_never,
)

from ..condition import assert_precondition

# Shortcut
getenv = os.getenv


ConfigError = ValidationError


def dict_merge(dct: Dict, merge_dct: Dict, model: Optional[BaseModel]):
    """ Recursive dict merge. Inspired by :meth:``dict.update()``, instead of
    updating only top-level keys, dict_merge recurses down into dicts nested
    to an arbitrary depth, updating keys. The ``merge_dct`` is merged into
    ``dct``.
    :param dct: dict onto which the merge is executed
    :param merge_dct: dct merged into dct
    :return: None

    Note: take care that plain dict fields are NOT merget but replaced
    like any other field wich is not a model.
    """
    for k, v in merge_dct.items():
        if (k in model.__dict__ and isinstance(model.__dict__[k], BaseModel)) \
            and (k in dct and isinstance(dct[k], dict)
            and isinstance(v, dict)):

            dict_merge(dct[k], merge_dct[k], model.__dict__[k])
        else:
            dct[k] = merge_dct[k]


def read_config(cfgfile: Path, loads: Callable[[str], Dict], **kwds) -> Dict[str, JsonValue]:
    """ Generic config reader
    """
    cfgfile = Path(cfgfile)
    # Load the toml file
    with cfgfile.open() as f:
        content = f.read()
        if kwds:
            from string import Template
            content = Template(content).substitute(kwds)
        return loads(content)


def read_config_toml(cfgfile: Path, **kwds) -> Dict:
    """ Read toml configuration from file
    """
    if sys.version_info < (3, 11):
        from tomli import loads  # type: ignore
    else:
        from tomllib import loads

    return read_config(cfgfile, loads=loads, **kwds)


# Base classe for configuration models
class ConfigBase(BaseModel, frozen=True, extra='forbid'):
    pass


class SectionExists(ValueError):
    pass


CreateDefault = object()

config_version = metadata.version('py_qgis_contrib')


#
# The base model for the config settings
#
class ConfigSettings(BaseSettings):
    model_config = SettingsConfigDict(
        frozen=True,
        extra='ignore',
        env_nested_delimiter='__',
        env_prefix='conf_',
        secrets_dir=getenv('SETTINGS_SECRETS_DIR', '/run/secrets'),
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            file_secret_settings,
        )


class ConfBuilder:
    #
    # Allow incrementally build configuration
    # It may be used together weth the config proxy
    # in order to propagate modification of the configuration
    #

    _global_sections: ClassVar[Dict] = {}

    _trace_output = TypeAdapter(bool).validate_python(
        os.getenv('PY_QGIS_CONFSERVICE_TRACE', 'no'),
    )

    def __init__(self):

        self._sections = self._global_sections.copy()
        self._model = None
        self._conf = None
        self._model_changed = True
        self._timestamp = 0

    @property
    def version(self):
        return config_version

    @classmethod
    def _trace(cls, *args):
        if cls._trace_output:
            print("==CONFSERVICE:", *args, file=sys.stderr, flush=True)  # noqa T201

    def _create_base_model(self) -> Type[BaseModel]:
        def _model(model):
            assert_precondition(isinstance(model, Tuple))
            match model:
                case (m,):
                    return (m, m())
                case (m, other):
                    return (m, other)
                case _ as unreachable:
                    assert_never(unreachable)

        return create_model(
            "_BaseConfig",
            __base__=ConfigSettings,
            **{name: _model(model) for name, model in self._sections.items()},
        )

    def _get_model(self) -> Type[ConfigSettings]:
        if self._model_changed or not self._model:
            self._model = self._create_base_model()
            self._model_changed = False

        return self._model

    @property
    def last_modified(self) -> float:
        return self._timestamp

    def validate(self, obj: Dict) -> ConfigSettings:
        """ Validate the configuration against
            configuration models
        """
        _BaseConfig = self._get_model()
        _conf = _BaseConfig.model_validate(obj, strict=True)

        self._conf = _conf
        # Update timestamp so that we can check update in
        # proxy
        self._timestamp = time()
        return _conf

    def update_config(self, obj: Optional[Dict] = None) -> ConfigSettings:
        """ Update the configuration
        """
        if self._model_changed or obj:
            if self._conf:
                data = self._conf.model_dump()
                if obj:
                    dict_merge(data, obj, self._conf)
            else:
                data = obj or {}

            self.validate(data)
        return self._conf

    def json_schema(self) -> Dict[str, Any]:
        return self._get_model().model_json_schema()

    def dump_toml_schema(self, s: IO):
        """ Dump the configuration as
            toml 'schema' for documentation purpose
        """
        from . import _toml
        _toml.dump_model_toml(s, self._get_model())

    def add_section(
        self,
        name: str,
        model: Type | TypeAlias,
        field: Any = CreateDefault,  # noqa ANN401
        replace: bool = False,
    ):
        self._trace("Adding section:", name)
        if not replace and name in self._sections:
            raise SectionExists(name)
        self._sections[name] = (model,) if field is CreateDefault else (model, field)
        self._model_changed = True

    @property
    def conf(self):
        self.update_config()
        return self._conf


#
# Config service
#

def section(
    name: str,
    *,
    field: Any = CreateDefault,  # noqa ANN401
) -> Callable:
    """ Decorator for config section definition

        Store section that will be initialized with builder
        instance

        @config.section("server")
        class ServerConfig(config.ConfigBase):
            ...
    """
    ConfBuilder._trace("Adding section:", name)
    if name in ConfBuilder._global_sections:
        raise SectionExists(name)

    def wrapper(model):
        ConfBuilder._global_sections[name] = (model,) if field is CreateDefault else (model, field)
        return model
    return wrapper


#
# Config Proxy
#

T = TypeVar('T', bound=ConfigBase)


class ConfigProxy(Generic[T]):
    """ Proxy to sub configuration

        Give access to sub-configuration from the confservice.
        This allows to retrieve configuration changes when reloading
        the global configuration.

        Some services may be initialised with sub configuration, this allow
        effective testing without dragging arount all the global configuration managment.

        The proxy mock acces to a sub-configuration as if it was the configuration itself.
        Because it access the global service under the hood, changes to global configuration
        are reflected.
    """

    def __init__(
            self,
            builder: ConfBuilder,
            configpath: str,
            *,
            default: Optional[T] = None,
    ):
        self._timestamp = -1
        self._builder = builder
        self._configpath = configpath
        if default:
            self._conf = default
        else:
            self.__update()

    @property
    def last_modified(self) -> float:
        return self._timestamp

    @property
    def builder(self) -> ConfBuilder:
        return self._builder

    @property
    def service(self) -> ConfBuilder:
        return self._builder

    def model_dump_json(self) -> str:
        return self.__update().model_dump_json()

    def __update(self) -> ConfigBase:
        if self._builder._timestamp > self._timestamp:
            self._timestamp = self._builder._timestamp
            self._conf = self._builder.conf
            for attr in self._configpath.split('.'):
                if attr:
                    self._conf = getattr(self._conf, attr)

        return self._conf

    def __getattr__(self, name):
        attr = getattr(self.__update(), name)
        if isinstance(attr, ConfigBase):
            # Wrap Config instance in ConfigProxy
            attr = ConfigProxy(
                self._builder,
                self._configpath + '.' + name,
                default=attr,
            )
        return attr
