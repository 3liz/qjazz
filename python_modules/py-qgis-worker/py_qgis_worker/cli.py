import sys
import asyncio
import click

from pathlib import Path
from typing_extensions import Optional
from py_qgis_contrib.core import logger
from py_qgis_contrib.core import config

from .config import WorkerConfig
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
            location=str(configpath.parent.absolute())
        )
    else:
        cnf = {}
    try:
        config.confservice.validate(cnf)
    except config.ConfigError as err:
        print("Configuration error:", err)
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
    envvar="QGIS_GRPC_CONFIGFILE",
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
    envvar="QGIS_GRPC_CONFIGFILE",
    help="configuration file",
    type=click.Path(
        exists=True,
        readable=True,
        dir_okay=False,
        path_type=Path
    ),
)
@click.option(
    "--num-workers", "-n",
    envvar="QGIS_GRPC_NUM_WORKERS",
    default=1,
    help="Number of workers to run",
)
def serve_grpc(configpath: Optional[Path], num_workers):
    """ Run grpc server
    """
    conf = load_configuration(configpath)
    logger.setup_log_handler(conf.logging.level)

    pool = WorkerPool(config.ConfigProxy(WORKER_SECTION), num_workers)
    pool.start()
    try:
        asyncio.run(serve(pool))
    finally:
        pool.terminate_and_join()
        logger.info("Server shutdown")


def main():
    cli_commands()
