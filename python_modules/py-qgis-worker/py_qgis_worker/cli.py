
import asyncio
import grpc
from ._grpc import api_pb2  # noqa
from ._grpc import api_pb2_grpc

from .service import ServiceApi


async def serve():
    server = grpc.aio.server()
    api_pb2_grpc.add_QgisWorkerServicer_to_server(ServiceApi(), server)
    listen_addr = "[::]:23456"
    server.add_insecure_port(listen_addr)
    await server.start()
    await server.wait_for_termination()


def main():
    asyncio.run(serve())
