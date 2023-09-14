import asyncio
import signal
import grpc

from contextlib import asynccontextmanager

from ._grpc import api_pb2_grpc

from grpc_health.v1 import health_pb2
from grpc_health.v1._async import HealthServicer
from grpc_health.v1.health_pb2_grpc import add_HealthServicer_to_server

from py_qgis_contrib.core import logger

from .config import WorkerConfig
from .service import QgisServer, QgisAdmin
from .pool import WorkerPool


async def serve(pool):
    """ Run server from pool
    """
    await pool.initialize()

    server = grpc.aio.server()

    # Configure Health check
    health_servicer = HealthServicer()
    add_HealthServicer_to_server(health_servicer, server)

    # Add services
    api_pb2_grpc.add_QgisServerServicer_to_server(QgisServer(pool), server)
    api_pb2_grpc.add_QgisAdminServicer_to_server(QgisAdmin(pool, health_servicer), server)

    await health_servicer.set("QgisServer", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("QgisAdmin", health_pb2.HealthCheckResponse.SERVING)

    for listen in pool.config.listen:
        match listen:
            case (iface, port):
                listen_addr = f"{iface}:{port}"
            case socket:
                listen_addr = socket
        logger.info("Listening on port: %s", listen_addr)
        server.add_insecure_port(listen_addr)

    shutdown_grace_period = pool.config.shutdown_grace_period
    max_failure_pressure = pool.config.max_worker_failure_pressure

    def _term(message, graceful: bool):
        logger.info(message)
        if graceful:
            logger.info("Entering graceful shutdown of %d s", shutdown_grace_period)
            loop.create_task(health_servicer.enter_graceful_shutdown())
            loop.create_task(server.stop(shutdown_grace_period))
        else:
            loop.create_task(server.stop(None))

    def _sigchild_handler():
        pressure = pool.worker_failure_pressure
        if pressure >= max_failure_pressure:
            logger.critical("Max worker failure reached, terminating...")
            _term("Child process terminated", False)
        else:
            logger.warning("Child process terminated (pressure: %s", pressure)

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, lambda: _term("Server terminated", True))
    loop.add_signal_handler(signal.SIGINT, lambda: _term("Server interrupted", False))
    loop.add_signal_handler(signal.SIGCHLD, _sigchild_handler)

    await server.start()
    await server.wait_for_termination()
