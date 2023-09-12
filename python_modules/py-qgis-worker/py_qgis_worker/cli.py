import sys
import asyncio
import grpc
import signal
from ._grpc import api_pb2  # noqa
from ._grpc import api_pb2_grpc

from .service import RpcService
from .worker import Worker
from .config import WorkerConfig

import click

from py_qgis_contrib.core import logger
from py_qgis_contrib.core import config

from pathlib import Path

from typing_extensions import Optional


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


async def serve(worker):
    server = grpc.aio.server()
    servicer = RpcService(worker)

    await servicer.cache_worker_status()

    api_pb2_grpc.add_QgisWorkerServicer_to_server(servicer, server)
    for iface, port in worker.config.listen:
        listen_addr = f"{iface}:{port}"
        logger.info("Listening on port: %s", listen_addr)
        server.add_insecure_port(listen_addr)

    def _term(message):
        logger.info(message)
        loop.create_task(server.stop(20))

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, lambda: _term("Server terminated"))
    loop.add_signal_handler(signal.SIGINT, lambda: _term("Server interrupted"))
    loop.add_signal_handler(
        signal.SIGCHLD,
        lambda: _term("Child process terminated")
    )

    await server.start()
    await server.wait_for_termination()


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
@click.option("--schema", is_flag=True, help="Display configuration schema")
@click.option("--pretty", is_flag=True, help="Pretty format")
def print_config(conf: Optional[Path], schema: bool = False, pretty: bool = False):
    """ Display configuration and exit
    """
    import json
    indent = 4 if pretty else None
    if schema:
        json_schema = config.confservice.json_schema()
        print(json.dumps(json_schema, indent=indent))
    else:
        print(load_configuration(conf).model_dump_json(indent=indent))


@cli_commands.command('grpc')
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
def serve_grpc(configpath: Optional[Path]):
    """ Run grpc server
    """
    conf = load_configuration(configpath)
    logger.setup_log_handler(conf.logging.level)

    worker = Worker(config.ConfigProxy(WORKER_SECTION))
    worker.start()
    try:
        asyncio.run(serve(worker))
    finally:
        worker.terminate()
        worker.join()
        logger.info("Server shutdown")


def main():
    cli_commands()
