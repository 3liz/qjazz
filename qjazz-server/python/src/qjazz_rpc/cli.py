import os

from pathlib import Path
from typing import (
    Optional,
    Protocol,
    cast,
)

import click

from qjazz_core import config, logger

from .doc import Worker


class ConfigProtocol(Protocol):
    logging: logger.LoggingConfig
    worker: Worker

    def model_dump_json(self, indent: Optional[int] = None): ...


def load_configuration(configpath: Optional[Path]) -> ConfigProtocol:
    # Set high precedence to environment variables
    config.set_env_settings_option("first")

    confservice = config.ConfBuilder()
    confservice.add_section("worker", Worker)

    if configpath:
        confservice.validate(config.read_config_toml(configpath))
    else:
        env_config = os.getenv("QJAZZ_CONFIG_JSON")
        if env_config:
            import json

            confservice.validate(json.loads(env_config))
        else:
            confservice.validate({})

    return cast(ConfigProtocol, confservice.conf)


@click.group()
def cli():
    pass


@cli.command("version")
@click.option("--settings", is_flag=True, help="Show QGIS settings")
def print_version(settings: bool):
    """Print version and exit"""
    from qjazz_core import manifest, qgis

    short_commit = manifest.short_commit_id() or "n/a"

    click.echo(f"Qjazz version: {config.config_version} ({short_commit})\n")
    qgis.print_qgis_version(settings)


FilePathType = click.Path(
    exists=True,
    readable=True,
    dir_okay=False,
    path_type=Path,
)


@cli.command("config")
@click.option(
    "--conf",
    "-C",
    help="configuration file",
    type=FilePathType,
)
@click.option("--pretty", is_flag=True, help="Pretty format")
def print_config(conf: Optional[Path], pretty: bool = False):
    """Print configuration as json and exit"""
    indent = 4 if pretty else None
    click.echo(load_configuration(conf).model_dump_json(indent=indent))


@cli.command("install-plugins")
@click.option(
    "--conf",
    "-C",
    "configpath",
    help="configuration file",
    type=FilePathType,
)
@click.option("--force", is_flag=True, help="Force installation")
def install_plugins(configpath: Optional[Path], force: bool):
    """Install plugins"""
    conf = load_configuration(configpath)
    logger.setup_log_handler(conf.logging.level)

    from qjazz_core.qgis import install_plugins

    if force or conf.worker.qgis.plugins.install_mode == "auto":
        install_plugins(conf.worker.qgis.plugins)
    else:
        click.echo("Plugin installation set to manual: no plugins to install...")


if __name__ == "__main__":
    cli()
