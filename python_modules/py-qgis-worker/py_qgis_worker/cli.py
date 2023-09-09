import sys
import asyncio
import grpc
from ._grpc import api_pb2  # noqa
from ._grpc import api_pb2_grpc

from .service import RpcService
from .worker import Worker
from .config import WorkerConfig, ProjectsConfig

from . import messages

from py_qgis_contrib.core import logger

from pathlib import Path


def get_config():
    data = Path("./tests/data").absolute()
    return WorkerConfig(
        name="Test",
        projects=ProjectsConfig(
            trust_layer_metadata=True,
            disable_getprint=True,
            force_readonly_layers=True,
            search_paths={
                '/tests': str(data.joinpath("samples")),
                '/france': str(data.joinpath("france_parts")),
                '/montpellier': str(data.joinpath("montpellier")),
            },
        ),
    )


async def serve(worker):

    logger.info("Waiting for worker to start...")
    status, _ = await worker.io.send_message(messages.Ping())
    if status != 200:
        logger.error("Worker failed with error {status}")
        sys.exit(1)

    server = grpc.aio.server()
    api_pb2_grpc.add_QgisWorkerServicer_to_server(RpcService(worker), server)
    listen_addr = "[::]:23456"
    server.add_insecure_port(listen_addr)
    await server.start()
    await server.wait_for_termination()


def main():

    logger.setup_log_handler(logger.LogLevel.DEBUG)

    worker = Worker(get_config())
    worker.start()

    asyncio.run(serve(worker))
