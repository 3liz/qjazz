import os
import sys

from pathlib import Path
from typing import Optional

import click

from qjazz_contrib.core import config, manifest

PathType = click.Path(
    exists=True,
    readable=True,
    dir_okay=False,
    path_type=Path,
)


@click.group()
@click.version_option(
    package_name="qjazz-processes",
    message=f"Qjazz version: %(version)s ({manifest.short_commit_id() or 'n/a'})",
)
@click.option(
    "--env-settings",
    type=click.Choice(("disabled", "last", "first")),
    default="first",
    help="Environment variables precedence",
    show_default=True,
)
def main(env_settings: config.EnvSettingsOption):
    config.set_env_settings_option(env_settings)


@main.command("serve")
@click.option(
    "--conf",
    "-C",
    "configpath",
    type=PathType,
    help="Path to configuration file",
)
@click.option(
    "--loglevel",
    "-l",
    type=click.Choice(("error", "warning", "info", "debug")),
    default="info",
    help="Log level",
    show_default=True,
)
@click.option("--dump", is_flag=True, help="Dump config and exit")
def run_worker(configpath: Optional[Path], loglevel: str, dump: bool):
    """Start service"""
    from qjazz_processes.worker.config import CONFIG_ENV_PATH

    if configpath:
        os.environ[CONFIG_ENV_PATH] = str(configpath)

    if dump:
        from typing import cast

        from pydantic import BaseModel

        from qjazz_processes.worker.config import load_configuration

        conf = cast(BaseModel, load_configuration())
        click.echo(conf.model_dump_json(indent=4))
    else:
        from .jobs import app
        app.start_worker(loglevel=loglevel)


@main.command("install-plugins")
@click.option(
    "--conf",
    "-C",
    "configpath",
    type=PathType,
    help="Path to configuration file",
)
@click.option("--force", is_flag=True, help="Force installation")
def install_plugins(configpath: Optional[Path], force: bool):
    """Install plugins"""
    from qjazz_contrib.core import logger
    from qjazz_processes.worker.config import CONFIG_ENV_PATH, load_configuration

    if configpath:
        os.environ[CONFIG_ENV_PATH] = str(configpath)

    try:
        conf = load_configuration()
    except FileNotFoundError as err:
        click.echo(f"FATAL: {err}", err=True)
        sys.exit(1)

    logger.setup_log_handler(conf.logging.level)

    if force or conf.processing.plugins.install_mode == "auto":
        from qjazz_contrib.core.qgis import install_plugins
        install_plugins(conf.processing.plugins)
    else:
        click.echo("Plugin installation set to manual: no plugins to install...")


@main.command("version")
@click.option("--settings", is_flag=True, help="Show QGIS settings")
def print_version(settings: bool):
    """Show GIS library versions"""
    from qjazz_contrib.core import manifest, qgis

    short_commit = manifest.short_commit_id() or "n/a"

    click.echo(f"Qjazz version: {config.config_version} ({short_commit})\n")
    qgis.print_qgis_version(settings)


main()
