import asyncio
import sys

from functools import wraps
from pathlib import Path
from typing import Optional, cast

import click

from .config import (
    ConfigProto,
    confservice,
    load_configuration,
)

FilePathType = click.Path(
    exists=True,
    readable=True,
    dir_okay=False,
    path_type=Path,
)


@click.group()
def cli_commands():
    pass


@cli_commands.command('config')
@click.option(
    "--conf", "-C", "configpath",
    help="configuration file",
    type=FilePathType,
)
@click.option("--schema", is_flag=True, help="Print configuration schema")
@click.option(
    "--format", "out_fmt",
    type=click.Choice(("json", "yaml", "toml")),
    default="json",
    help="Output format (--schema only)",
)
@click.option("--pretty", is_flag=True, help="Pretty format")
def print_config(
    configpath: Optional[Path],
    out_fmt: str,
    schema: bool = False,
    pretty: bool = False,
):
    """ Print configuration as json and exit
    """
    import json

    indent = 4 if pretty else None
    if schema:
        match out_fmt:
            case 'json':
                json_schema = confservice.json_schema()
                indent = 4 if pretty else None
                click.echo(json.dumps(json_schema, indent=indent))
            case 'yaml':
                from ruamel.yaml import YAML
                json_schema = confservice.json_schema()
                yaml = YAML()
                yaml.dump(json_schema, sys.stdout)
            case 'toml':
                confservice.dump_toml_schema(sys.stdout)
    else:
        click.echo(load_configuration(configpath).model_dump_json(indent=indent))


if __name__ == '__main__':
    cli_commands()
