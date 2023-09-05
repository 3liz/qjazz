import grpc
from ._grpc import api_pb2
from ._grpc import api_pb2_grpc


class ServiceApi(api_pb2_grpc.QgisWorkerServicer):
    """ Worker API
    """
    async def Ping(
        self,
        request: api_pb2.PingRequest,
        context: grpc.aio.ServicerContext,
    ) -> api_pb2.PingReply:
        """  Simple ping request
        """
        echo = request.echo
        return api_pb2.PingReply(echo=echo)
