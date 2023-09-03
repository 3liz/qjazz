
import asyncio
import grpc
from _grpc import api_pb2
from _grpc import api_pb2_grpc


class Worker(api_pb2_grpc.QgisWorkerServicer):
    async def Ping(
        self,
        request: api_pb2.PingRequest,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.PingReply:
        echo = request.echo
        return api_pb2.PingReply(message=echo)


async def serve():
    server = grpc.aio.server()
    api_pb2_grpc.add_QgisWorkerServicer_to_server(Worker(), server)
    listen_addr = "[::]:23456"
    server.add_insecure_port(listen_addr)
    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
