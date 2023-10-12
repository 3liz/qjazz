import sys  # noqa
import asyncio
import click

from typing_extensions import (
    Optional,
)

from pathlib import Path

from py_qgis_contrib.core import config, logger

from .config import load_configuration, add_configuration_sections
from .server import serve

add_configuration_sections()


@click.group()
def cli_commands():
    pass


@cli_commands.command('serve')
@click.option(
    "--conf", "-C", "configpath",
    envvar="QGIS_HTTP_CONFIGFILE",
    help="configuration file",
    type=click.Path(
        exists=True,
        readable=True,
        dir_okay=False,
        path_type=Path
    ),
)
def serve_http(configpath: Path):

    conf = load_configuration(configpath)
    logger.setup_log_handler(conf.logging.level)

    asyncio.run(serve(conf))


@cli_commands.command('config')
@click.option(
    "--conf", "-C", "configpath",
    envvar="QGIS_HTTP_CONFIGFILE",
    help="configuration file",
    type=click.Path(
        exists=True,
        readable=True,
        dir_okay=False,
        path_type=Path
    ),
)
@click.option("--schema", is_flag=True, help="Print configuration schema")
@click.option("--pretty", is_flag=True, help="Pretty format")
def print_config(configpath: Optional[Path], schema: bool = False, pretty: bool = False):
    """ Print configuration as json and exit
    """
    import json

    indent = 4 if pretty else None
    if schema:
        json_schema = config.confservice.json_schema()
        print(json.dumps(json_schema, indent=indent))
    else:
        print(load_configuration(configpath).model_dump_json(indent=indent))


def main():
    cli_commands()
