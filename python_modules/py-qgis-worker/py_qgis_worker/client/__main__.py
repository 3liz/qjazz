""" gRPC Client test
"""
import grpc
from .._grpc import api_pb2
from .._grpc import api_pb2_grpc


def run():
    # NOTE(gRPC Python Team): .close() is possible on a channel and should be
    # used in circumstances in which the with statement does not fit the needs
    # of the code.
    #
    # For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html
    with grpc.insecure_channel(
        target="localhost:23456",
        options=[
            ("grpc.lb_policy_name", "pick_first"),
            ("grpc.enable_retries", 0),
            ("grpc.keepalive_timeout_ms", 10000),
        ],
    ) as channel:
        stub = api_pb2_grpc.QgisWorkerStub(channel)
        # Timeout in seconds.
        # Please refer gRPC Python documents for more detail. https://grpc.io/grpc/python/grpc.html
        response = stub.Ping(
            api_pb2.PingRequest(echo="Hello"), timeout=10
        )
    print("ECHO:", response.echo)


run()
