import sys

from pathlib import Path
from types import SimpleNamespace

import click

from click import echo
from pydantic import (
    JsonValue,
    TypeAdapter,
)
from typing_extensions import Optional

from py_qgis_contrib.core import logger

from .server import confservice, load_configuration, serve

FilePathType = click.Path(
    exists=True,
    readable=True,
    dir_okay=False,
    path_type=Path,
)


@click.group()
@click.option(
    "--config", "-C", "configpath",
    help="Path to configuration file",
    type=FilePathType,
    envvar="PY_QGIS_PROCESSES_SERVER_CONFIG",
)
@click.option("--verbose", "-v", is_flag=True, help="Set verbose output")
@click.pass_context
def cli_commands(
    ctx: click.Context,
    configpath: Optional[Path],
    verbose: bool = False,
):
    ctx.obj = SimpleNamespace(
        configpath=configpath,
        verbose=verbose,
    )


@cli_commands.command('serve')
@click.pass_context
def run_server(ctx: click.Context):
    """ Run server
    """
    conf = load_configuration(ctx.obj.configpath)
    logger.setup_log_handler(
        logger.LogLevel.TRACE if ctx.obj.verbose else conf.logging.level,
    )

    serve(conf)


@cli_commands.command('config')
@click.option("--schema", is_flag=True, help="Print configuration schema")
@click.option(
    "--format", "out_format",
    type=click.Choice(("json", "yaml", "toml")),
    default="json",
    help="Output format (schema only)",
)
@click.pass_context
def dump_config(
    ctx: click.Context,
    out_format: str,
    schema: bool = False,
):
    """ Display configuration
    """
    if schema:
        match out_format:
            case 'json':
                json_schema = confservice.json_schema()
                echo(
                    TypeAdapter(JsonValue).dump_json(
                        json_schema,  # type: ignore [arg-type]
                        indent=4,
                    ),
                )
            case 'yaml':
                from ruamel.yaml import YAML
                json_schema = confservice.json_schema()
                yaml = YAML()
                yaml.dump(json_schema, sys.stdout)
            case 'toml':
                confservice.dump_toml_schema(sys.stdout)
    else:
        conf = load_configuration(ctx.obj.configpath)
        echo(conf.model_dump_json(indent=4))


@cli_commands.command('openapi')
@click.option("--yaml", "to_yaml", is_flag=True, help="Output as yaml (default: json)")
def dump_swagger_doc(to_yaml: bool):
    """  Output swagger api documentation
    """
    from .server import swagger_model

    doc = swagger_model()
    if to_yaml:
        from ruamel.yaml import YAML
        yaml = YAML()
        yaml.dump(doc.model_dump(), sys.stdout)
    else:
        click.echo(doc.model_dump_json())


def main():
    cli_commands()
