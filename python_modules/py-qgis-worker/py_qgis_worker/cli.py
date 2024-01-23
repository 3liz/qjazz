import asyncio
import os
import sys

from pathlib import Path

import click

from typing_extensions import Any, Optional, cast

from py_qgis_contrib.core import config, logger

from .config import ENV_CONFIGFILE, WorkerConfig
from .pool import WorkerPool
from .server import serve

WORKER_SECTION = 'worker'

# Add the `[worker]` configuration section
config.confservice.add_section(WORKER_SECTION, WorkerConfig)


#
# Load configuration file
#
def load_configuration(configpath: Optional[Path]) -> config.Config:
    if configpath:
        cnf = config.read_config_toml(
            configpath,
            location=str(configpath.parent.absolute()),
        )
        # Needed when reloading configuration
        os.environ[ENV_CONFIGFILE] = configpath.as_posix()
    else:
        cnf = {}
    try:
        config.confservice.validate(cnf)
        # Load external configuration if requested
        config_url = config.confservice.conf.config_url
        if config_url.is_set():
            click.echo(
                f"** Loading initial configuration from <{config_url.url}> **",
                file=sys.stderr,
            )
            cnf = asyncio.run(config_url.load_configuration())
            config.confservice.update_config(cnf)
    except config.ConfigError as err:
        click.echo(f"Configuration error: {err}", file=sys.stderr)
        sys.exit(1)
    return config.confservice.conf


@click.group()
def cli_commands():
    pass


@cli_commands.command('version')
@click.option("--settings", is_flag=True, help="Show Qgis settings")
def print_version(settings: bool):
    """ Print version and exit
    """
    from py_qgis_contrib.core import qgis
    qgis.print_qgis_version(settings)


FilePathType = click.Path(
    exists=True,
    readable=True,
    dir_okay=False,
    path_type=Path,
)


@cli_commands.command('config')
@click.option(
    "--conf", "-C",
    envvar=ENV_CONFIGFILE,
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
def print_config(conf: Optional[Path], out_fmt: str, schema: bool = False, pretty: bool = False):
    """ Print configuration as json and exit
    """
    import json
    indent = 4 if pretty else None
    if schema:
        match out_fmt:
            case 'json':
                json_schema = config.confservice.json_schema()
                indent = 4 if pretty else None
                click.echo(json.dumps(json_schema, indent=indent))
            case 'yaml':
                from ruamel.yaml import YAML
                json_schema = config.confservice.json_schema()
                yaml = YAML()
                yaml.dump(json_schema, sys.stdout)
            case 'toml':
                config.confservice.dump_toml_schema(sys.stdout)
    else:
        click.echo(load_configuration(conf).model_dump_json(indent=indent))


@cli_commands.command("plugins")
@click.option(
    "--conf", "-C", "configpath",
    envvar=ENV_CONFIGFILE,
    help="configuration file",
    type=FilePathType,
)
def install_plugins(configpath: Optional[Path]):
    """ Install plugins
    """
    conf: Any = load_configuration(configpath)
    logger.setup_log_handler(conf.logging.level)

    from py_qgis_contrib.core.qgis import install_plugins
    install_plugins(conf.worker.plugins)


@cli_commands.command('serve')
@click.option(
    "--conf", "-C", "configpath",
    envvar=ENV_CONFIGFILE,
    help="configuration file",
    type=FilePathType,
)
def serve_grpc(configpath: Optional[Path]):
    """ Run grpc server
    """
    conf: Any = load_configuration(configpath)
    logger.setup_log_handler(conf.logging.level)

    conf.worker.plugins.do_install()

    pool = WorkerPool(cast(WorkerConfig, config.ConfigProxy(WORKER_SECTION)))
    pool.start()
    try:
        asyncio.run(serve(pool))
    finally:
        pool.terminate_and_join()
        logger.info("Server shutdown")


def main():
    cli_commands()
