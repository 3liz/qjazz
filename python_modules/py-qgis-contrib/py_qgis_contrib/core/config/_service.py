#
# Copyright 2018 3liz
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

Source searched for configuration values:

1. Argument passed to configuration
2. Environment variables starting with `conf_`
3. Variables loaded from a dotenv (.env)
4. Variables loaded from the Docker secrets directory (/run/secrets)
5. he default field values

"""
import os

from pathlib import Path
from time import time

from pydantic import (
    BaseModel,
    Field,
    PlainSerializer,
    PlainValidator,
    ValidationError,
    create_model,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import (
    IO,
    Annotated,
    Any,
    Callable,
    Dict,
    Optional,
    Tuple,
    Type,
)

from .. import componentmanager

# Shortcut
getenv = os.getenv


ConfigError = ValidationError


def dict_merge(dct, merge_dct):
    """ Recursive dict merge. Inspired by :meth:``dict.update()``, instead of
    updating only top-level keys, dict_merge recurses down into dicts nested
    to an arbitrary depth, updating keys. The ``merge_dct`` is merged into
    ``dct``.
    :param dct: dict onto which the merge is executed
    :param merge_dct: dct merged into dct
    :return: None
    """
    for k, v in merge_dct.items():
        if (k in dct and isinstance(dct[k], dict) and isinstance(merge_dct[k], dict)):
            dict_merge(dct[k], merge_dct[k])
        else:
            dct[k] = merge_dct[k]


def read_config(cfgfile: Path, loads: Callable[[str], Dict], **kwds) -> Dict:
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
    try:
        # Python 3.11+
        import tomllib as toml
    except ModuleNotFoundError:
        import tomli as toml

    return read_config(cfgfile, loads=toml.loads, **kwds)


def read_config_json(cfgfile: Path, **kwds) -> Dict:
    """ Read Json configuration from file
    """
    import json
    return read_config(cfgfile, loads=json.loads, **kwds)


def read_config_yaml(cfgfile: Path, **kwds) -> Dict:
    """ Read Yaml configuration from file
    """
    from ruamel.yaml import YAML
    yaml = YAML(typ='safe')
    return read_config(cfgfile, loads=yaml.load, **kwds)


# Base classe for configuration models
class Config(BaseModel, frozen=True, extra='forbid'):
    pass


CONFIG_SERVICE_CONTRACTID = '@3liz.org/config-service;1'


@componentmanager.register_factory(CONFIG_SERVICE_CONTRACTID)
class ConfigService:

    def __init__(self):

        from importlib import metadata

        self._configs = {}
        self._model = None
        self._conf = None
        self._model_changed = True
        self._timestamp = 0
        self._env_prefix = 'conf_'
        self._default_confdir = None
        self._version = metadata.version('py_qgis_contrib')

    def _create_base_model(self, base: Type[BaseModel]):
        def _model(model):
            if isinstance(model, Tuple):
                return model
            else:
                return model, model()

        return create_model(
            "BaseConfig",
            __base__=base,
            **{name: _model(model) for name, model in self._configs.items()}
        )

    def _create_model(self) -> BaseSettings:
        if self._model_changed or not self._model:

            class BaseConfig(BaseSettings, frozen=True, extra='forbid'):
                model_config = SettingsConfigDict(
                    env_nested_delimiter='__',
                    env_prefix=self._env_prefix,
                )

                # XXX Use user dir
                confdir: Annotated[
                    Path,
                    PlainValidator(lambda v: Path(v)),
                    PlainSerializer(lambda x: str(x), return_type=str),
                ] = Field(
                    default=self._default_confdir or os.getcwd(),
                    title="Search path for configuration files",
                )

            self._model = self._create_base_model(BaseConfig)
            self._model_changed = False

        return self._model

    @property
    def version(self):
        return self._version

    @property
    def last_modified(self) -> float:
        return self._timestamp

    def validate(
            self, obj: Dict,
            default_confdir: Optional[Path] = None,
            env_prefix: Optional[str] = None,
    ):
        """ Validate the configuration against
            configuration models
        """
        self._env_prefix = env_prefix or self._env_prefix
        self._default_confdir = default_confdir or self._default_confdir

        BaseConfig = self._create_model()
        _conf = BaseConfig.model_validate(obj, strict=True)

        self._conf = _conf
        # Update timestamp so that we can check update in
        # proxy
        self._timestamp = time()

    def update_config(self, obj: Optional[Dict] = None):
        """ Update the configuration
        """
        if self._model_changed or obj:
            data = self._conf.model_dump() if self._conf else {}
            if obj:
                dict_merge(data, obj)
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
        model: Type[Config] | Tuple[Type, Any],
        replace: bool = False,
    ):
        if not replace and name in self._configs:
            raise ValueError(f"Config {name} already defined in: {self._configs[name]}")
        self._configs[name] = model
        self._model_changed = True

    @property
    def conf(self):
        self.update_config()
        return self._conf


confservice = componentmanager.get_service(CONFIG_SERVICE_CONTRACTID)


def section(name: str, instance: Optional[ConfigService] = None):
    """ Decorator for config section definition

        @config.section("server")
        class ServerConfig(config.Config):
            model_config = SettingsConfigDict(env_prefix='conf_server_')
    """
    service = instance or confservice

    def wrapper(model: Config):
        service.add_section(name, model)
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
                self._configpath+'.'+name,
                self._confservice,
                _default=attr,
            )
        return attr
