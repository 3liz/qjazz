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

from time import time
from pathlib import Path
from pydantic import create_model, BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from typing_extensions import Optional, Dict, Type

from .. import componentmanager

# Shortcut
getenv = os.getenv


ConfigError = ValidationError


def read_config_toml(self, cfgfile: Path) -> Dict:
    """ Read configuration from file
    """
    try:
        # Python 3.11+
        import tomllib as toml
    except ModuleNotFoundError:
        import tomli as toml

    cfgfile = Path(cfgfile)
    # Load the toml file
    with cfgfile.open() as f:
        return toml.loads(f.read())


# Base classe for configuration models
class Config(BaseModel, frozen=True):
    pass


# XXX Change name
DEFAULT_APPLICATION_NAME = 'py-qgis-server'

CONFIG_SERVICE_CONTRACTID = '@3liz.org/config-service;1'


@componentmanager.register_factory(CONFIG_SERVICE_CONTRACTID)
class ConfigService:

    def __init__(self):
        self._configs = {}
        self._model = None
        self._conf = None
        self._model_changed = True
        self._timestamp = 0

    def _create_model(self, base) -> BaseSettings:
        if self._model_changed or not self._model:
            self._model = create_model(
                "BaseConfig",
                __base__=base,
                **{name: (model, model()) for name, model in self._configs.items()}
            )
        return self._model

    def validate(
            self, obj: Dict,
            application_name: str = DEFAULT_APPLICATION_NAME,
            env_prefix: Optional[str] = None,
    ):
        """ Validate the configuration against
            configuration models
        """
        env_prefix = env_prefix or 'conf_'

        class BaseConfig(BaseSettings, frozen=True):
            model_config = SettingsConfigDict(
                env_nested_delimiter='__',
                env_prefix=env_prefix,
            )

            # XXX Use user dir
            confdir: Path = Field(
                default=Path(f'/etc/{application_name}'),
                title="Search path for configuration files",
            )

        BaseConfig = self._create_model(BaseConfig)
        _conf = BaseConfig.model_validate(obj)

        self._conf = _conf
        self._model_changed = False
        # Update timestamp so that we can check update in
        # proxy
        self._timestamp = time()

    def update_config(self):
        """ Update the configuration
        """
        if self._model_changed:
            data = self._conf.model_dump() if self._conf else {}
            self.validate(data)

    def json_schema(self) -> Dict:
        return self._create_model(BaseSettings).model_json_schema()

    def add_section(self, name: str, model: Type[Config], replace: bool = False):
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

    def __update(self) -> Config:
        if self._confservice._timestamp > self._timestamp:
            self._conf = self._confservice.conf
            for attr in self._configpath.split('.'):
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
