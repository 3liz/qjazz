import asyncio
import signal
import traceback

from pathlib import Path

import grpc

from grpc_health.v1 import health_pb2
from grpc_health.v1._async import HealthServicer
from grpc_health.v1.health_pb2_grpc import add_HealthServicer_to_server
from typing_extensions import Optional

from py_qgis_contrib.core import logger

from ._grpc import api_pb2_grpc
from .restore import create_restore_object
from .service import QgisAdmin, QgisServer


async def serve(pool):
    """ Run server from pool
    """
    # Init pool queue
    await pool.initialize()

    # Restore cache if needed
    restore = create_restore_object()
    await restore.restore(pool)

    server = grpc.aio.server()

    # Configure Health check
    health_servicer = HealthServicer()
    add_HealthServicer_to_server(health_servicer, server)

    # Add services
    api_pb2_grpc.add_QgisServerServicer_to_server(QgisServer(pool), server)
    api_pb2_grpc.add_QgisAdminServicer_to_server(
        QgisAdmin(pool, health_servicer, restore),
        server,
    )

    await health_servicer.set("QgisServer", health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("QgisAdmin", health_pb2.HealthCheckResponse.SERVING)

    for iface in pool.config.interfaces:
        match iface.listen:
            case (addr, port):
                listen_addr = f"{addr}:{port}"
            case socket:
                listen_addr = socket

        if iface.use_ssl:
            # Load certificates
            def _read_if(f: Path) -> Optional[bytes]:
                with f.open('rb') as fp:
                    return fp.read()

            ssl = iface.ssl

            logger.info("Listening on port: %s (SSL on)", listen_addr)
            server.add_secure_port(
                listen_addr,
                grpc.ssl_server_credentials(
                    [[_read_if(ssl.keyfile), _read_if(ssl.certfile)]],
                    # Client authentification
                    root_certificates=_read_if(ssl.cafile) if ssl.cafile else None,
                    require_client_auth=ssl.cafile is not None,
                ),
            )
        else:
            logger.info("Listening on port: %s", listen_addr)
            server.add_insecure_port(listen_addr)

    async def graceful_shutdown(message: str, graceful: bool):
        logger.info(message)
        if graceful:
            shutdown_grace_period = pool.config.shutdown_grace_period
            logger.info("Entering graceful shutdown of %d s", shutdown_grace_period)
            await health_servicer.enter_graceful_shutdown()
            await server.stop(shutdown_grace_period)
        else:
            await server.stop(None)

    # Keep ref of tasks
    # see https://docs.python.org/3.11/library/asyncio-task.html#asyncio.create_task
    background_tasks = set()

    def _term(message: str, graceful: bool):
        task = asyncio.create_task(graceful_shutdown(message, graceful))
        background_tasks.add(task)

    def _sigchild_handler():
        pressure = pool.worker_failure_pressure
        max_failure_pressure = pool.config.max_processes_failure_pressure
        if pressure >= max_failure_pressure:
            logger.critical("Max worker failure reached, terminating...")
            _term("Child process terminated", False)
        else:
            logger.warning("Child process terminated (pressure: %s", pressure)

    # Set scaling task
    async def autoscale():
        while True:
            try:
                scale_period = pool.config.scale_period
                await asyncio.sleep(scale_period or 30)
                if not scale_period:
                    continue
                await pool.maintain_pool(restore.projects)
            except Exception:
                logger.error("Scaling failed: %s", traceback.format_exc())

    background_tasks.add(asyncio.create_task(autoscale()))

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, lambda: _term("Server terminated", True))
    loop.add_signal_handler(signal.SIGINT, lambda: _term("Server interrupted", False))
    loop.add_signal_handler(signal.SIGCHLD, _sigchild_handler)

    await server.start()
    await server.wait_for_termination()
