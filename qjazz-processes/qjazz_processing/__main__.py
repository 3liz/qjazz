import os
import sys

from pathlib import Path
from typing import Optional

import click

PathType = click.Path(
    exists=True,
    readable=True,
    dir_okay=False,
    path_type=Path,
)


@click.group()
def main():
    pass


@main.command("start")
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
)
@click.option("--dump", is_flag=True, help="Dump config and exit")
def run_worker(configpath: Optional[Path], loglevel: str, dump: bool):
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


main()
