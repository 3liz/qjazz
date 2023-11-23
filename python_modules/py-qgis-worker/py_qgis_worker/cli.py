import asyncio
import os
import sys

from pathlib import Path

import click

from typing_extensions import Optional

from py_qgis_contrib.core import config, logger

from .config import ENV_CONFIGFILE, ENV_NUM_PROCESSES, WorkerConfig
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
            print(f"** Loading initial configuration from <{config_url.url}> **", flush=True)
            cnf = asyncio.run(config_url.load_configuration())
            config.confservice.update_config(cnf)
    except config.ConfigError as err:
        print("Configuration error:", err, file=sys.stderr, flush=True)
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


@cli_commands.command('config')
@click.option(
    "--conf", "-C",
    envvar=ENV_CONFIGFILE,
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
def print_config(conf: Optional[Path], schema: bool = False, pretty: bool = False):
    """ Print configuration as json and exit
    """
    import json
    indent = 4 if pretty else None
    if schema:
        json_schema = config.confservice.json_schema()
        print(json.dumps(json_schema, indent=indent))
    else:
        print(load_configuration(conf).model_dump_json(indent=indent))


@cli_commands.command('serve')
@click.option(
    "--conf", "-C", "configpath",
    envvar=ENV_CONFIGFILE,
    help="configuration file",
    type=click.Path(
        exists=True,
        readable=True,
        dir_okay=False,
        path_type=Path
    ),
)
@click.option(
    "--num-processes", "-n",
    envvar=ENV_NUM_PROCESSES,
    default=1,
    help="Number of qgis server processes to run",
)
def serve_grpc(configpath: Optional[Path], num_processes):
    """ Run grpc server
    """
    conf = load_configuration(configpath)
    logger.setup_log_handler(conf.logging.level)

    pool = WorkerPool(config.ConfigProxy(WORKER_SECTION), num_processes)
    pool.start()
    try:
        asyncio.run(serve(pool))
    finally:
        pool.terminate_and_join()
        logger.info("Server shutdown")


def main():
    cli_commands()
