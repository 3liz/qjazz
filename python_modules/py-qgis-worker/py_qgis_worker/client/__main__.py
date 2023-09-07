""" gRPC Client test
"""
import grpc
from .._grpc import api_pb2
from .._grpc import api_pb2_grpc

from google.protobuf.json_format import MessageToJson

import sys
import click

from pathlib import Path
from contextlib import contextmanager
from typing import (
    Optional,
    List,
)


@contextmanager
def connect():
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
        try:
            yield api_pb2_grpc.QgisWorkerStub(channel)
            # Timeout in seconds.
            # Please refer gRPC Python documents for more detail. https://grpc.io/grpc/python/grpc.html
        except grpc.RpcError as rpcerr:
            print("RPC ERROR:", rpcerr.code(), rpcerr.details(), file=sys.stderr)
            for (k, v) in rpcerr.trailing_metadata():
                print(k, ":", v, file=sys.stderr)


def print_metadata(metadata):
    status_code = "n/a"
    for k, v in metadata:
        if k == "x-reply-status-code":
            status_code = v
        elif k.startswith("x-reply-header-"):
            h = k.replace("x-reply-header-", "", 1)
            print(h.title(), ":", v, file=sys.stderr)
        elif k.startswith("x-"):
            print(k, ":", v, file=sys.stderr)
    print("Return code:", status_code, file=sys.stderr)


@click.group('commands')
def cli_commands():
    pass


@cli_commands.command("ows")
@click.argument('project', nargs=1)
@click.option("--service", help="OWS service name", required=True)
@click.option("--request", help="OWS request name", required=True)
@click.option("--version", help="OWS service version")
@click.option("--param", "-p", multiple=True, help="Parameters KEY=VALUE")
@click.option("--headers", "-H", is_flag=True, help="Show headers")
@click.option("--url", help="Origin url")
@click.option(
    "--output", "-o",
    help="Destination file",
    type=click.Path(dir_okay=False),
)
def ows_request(
    project: str,
    service: str,
    request: str,
    version: Optional[str],
    param: List[str],
    headers: bool,
    output: Optional[str],
    url: Optional[str],
):
    with connect() as stub:
        stream = stub.ExecuteOwsRequest(
            api_pb2.OwsRequest(
                service=service,
                request=request,
                target=project,
                url=url or "",
            ),
            timeout=10,
        )

        if headers:
            print_metadata(stream.initial_metadata())

        fp = Path(output).open("w") if output else sys.stdout
        for chunk in stream:
            print(chunk, file=fp)


@cli_commands.command("pull")
@click.argument('project', nargs=1)
@click.option("--headers", "-H", is_flag=True, help="Show headers")
def pull_project(project: str, headers: bool):
    """ Pull PROJECT in cache
    """
    with connect() as stub:
        resp = stub.PullProject(
            api_pb2.PullRequest(uri=project)
        )

        print(MessageToJson(resp))


cli_commands()
