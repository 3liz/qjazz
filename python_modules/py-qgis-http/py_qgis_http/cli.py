import sys  # noqa
import asyncio
import click

from typing_extensions import (
    Optional,
)

from pathlib import Path
from functools import wraps

from .config import (
    confservice,
    load_configuration,
    add_configuration_sections,
    ENV_CONFIGFILE,
)
from .server import serve

add_configuration_sections()


FilePathType = click.Path(
    exists=True,
    readable=True,
    dir_okay=False,
    path_type=Path,
)


# Workaround https://github.com/pallets/click/issues/295
def global_options():
    def _wrapper(f):
        @wraps(f)
        @click.option("--verbose", "-v", is_flag=True, help="Set verbose mode")
        @click.option(
            "--conf", "-C", "configpath",
            envvar=ENV_CONFIGFILE,
            help="configuration file",
            type=FilePathType,
        )
        def _inner(*args, **kwargs):
            return f(*args, **kwargs)
        return _inner
    return _wrapper


@click.group()
def cli_commands():
    pass


@cli_commands.command('serve')
@global_options()
def serve_http(configpath: Path, verbose: bool):

    from py_qgis_contrib.core.config import ConfigProxy

    print("Qgis HTTP middleware", confservice.version, flush=True)
    conf = load_configuration(configpath, verbose)
    conf = ConfigProxy("", _default=conf)
    asyncio.run(serve(conf))


@cli_commands.command('config')
@click.option("--schema", is_flag=True, help="Print configuration schema")
@click.option("--pretty", is_flag=True, help="Pretty format")
@global_options()
def print_config(
    configpath: Optional[Path],
    verbose: bool,
    schema: bool = False,
    pretty: bool = False,
):
    """ Print configuration as json and exit
    """
    import json

    indent = 4 if pretty else None
    if schema:
        json_schema = confservice.json_schema()
        print(json.dumps(json_schema, indent=indent))
    else:
        print(load_configuration(configpath, verbose).model_dump_json(indent=indent))


def main():
    cli_commands()
