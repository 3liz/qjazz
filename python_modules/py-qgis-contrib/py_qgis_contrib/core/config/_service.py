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

from pathlib import Path
from time import time

from pydantic import (
    BaseModel,
    JsonValue,
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
    Dict,
    Optional,
    Tuple,
    Type,
    TypeAlias,
    assert_never,
)

from .. import componentmanager
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
        from tomli import loads
    else:
        from tomllib import loads

    return read_config(cfgfile, loads=loads, **kwds)


# Base classe for configuration models
class Config(BaseModel, frozen=True, extra='forbid'):
    pass


class SectionExists(ValueError):
    pass


CONFIG_SERVICE_CONTRACTID = '@3liz.org/config-service;1'


CreateDefault = object()


@componentmanager.register_factory(CONFIG_SERVICE_CONTRACTID)
class ConfigService:

    def __init__(self):

        from importlib import metadata

        self._configs = {}
        self._model = None
        self._conf = None
        self._model_changed = True
        self._timestamp = 0
        self._version = metadata.version('py_qgis_contrib')
        self._baseconfig = None

        self._model_config = SettingsConfigDict(
            frozen=True,
            extra='forbid',
            env_nested_delimiter='__',
            env_prefix='conf_',
        )

        secrets_dir = getenv('SETTINGS_SECRETS_DIR', '/run/secrets')
        if Path(secrets_dir).exists():
            self._model_config.update(secrets_dir=secrets_dir)

    def _create_base_model(self, base: Type[BaseModel]) -> Type[BaseModel]:
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
            __base__=base,
            **{name: _model(model) for name, model in self._configs.items()},
        )

    def _init_base_settings(self) -> Type[BaseSettings]:
        if not self._baseconfig:
            class BaseConfig(BaseSettings):
                model_config = self._model_config

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

            self._baseconfig = BaseConfig
        return self._baseconfig

    def _create_model(self) -> BaseSettings:
        if self._model_changed or not self._model:
            self._model = self._create_base_model(self._init_base_settings())
            self._model_changed = False

        return self._model

    @property
    def version(self):
        return self._version

    @property
    def last_modified(self) -> float:
        return self._timestamp

    def validate(self, obj: Dict):
        """ Validate the configuration against
            configuration models
        """
        _BaseConfig = self._create_model()
        _conf = _BaseConfig.model_validate(obj, strict=True)

        self._conf = _conf
        # Update timestamp so that we can check update in
        # proxy
        self._timestamp = time()

    def update_config(self, obj: Optional[Dict] = None):
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

    def json_schema(self) -> Dict:
        return self._create_base_model(BaseSettings).model_json_schema()

    def dump_toml_schema(self, s: IO):
        """ Dump the configuration as
            toml 'schema' for documentation purpose
        """
        from . import _toml
        model = self._create_base_model(BaseSettings)
        _toml.dump_model_toml(s, model)

    def add_section(
        self,
        name: str,
        model: Type | TypeAlias,
        field: Any = CreateDefault,  # noqa ANN401
        replace: bool = False,
    ):
        if not replace and name in self._configs:
            raise SectionExists(name)
        self._configs[name] = (model,) if field is CreateDefault else (model, field)
        self._model_changed = True

    @property
    def conf(self):
        self.update_config()
        return self._conf


confservice = componentmanager.get_service(CONFIG_SERVICE_CONTRACTID)


def section(
    name: str,
    instance: Optional[ConfigService] = None,
    *,
    field: Any = CreateDefault,  # noqa ANN401
) -> Callable[[Type[Config]], Type[Config]]:
    """ Decorator for config section definition

        @config.section("server")
        class ServerConfig(config.Config):
            model_config = SettingsConfigDict(env_prefix='conf_server_')
    """
    service = instance or confservice

    def wrapper(model: Type[Config]) -> Type[Config]:
        service.add_section(name, model, field)
        return model
    return wrapper


#
# Config Proxy
#

class ConfigProxy:
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
            configpath: str,
            _confservice: Optional[ConfigService] = None,
            _default: Optional[Config] = None,
    ):
        self._timestamp = -1
        self._confservice = _confservice or confservice
        self._configpath = configpath
        if _default:
            self._conf = _default
        else:
            self.__update()

    @property
    def last_modified(self) -> float:
        return self._timestamp

    @property
    def service(self) -> ConfigService:
        return self._confservice

    def model_dump_json(self) -> str:
        return self.__update().model_dump_json()

    def __update(self) -> Config:
        if self._confservice._timestamp > self._timestamp:
            self._timestamp = self._confservice._timestamp
            self._conf = self._confservice.conf
            for attr in self._configpath.split('.'):
                if attr:
                    self._conf = getattr(self._conf, attr)

        return self._conf

    def __getattr__(self, name):
        attr = getattr(self.__update(), name)
        if isinstance(attr, Config):
            # Wrap Config instance in ConfigProxy
            attr = ConfigProxy(
                self._configpath + '.' + name,
                self._confservice,
                _default=attr,
            )
        return attr
