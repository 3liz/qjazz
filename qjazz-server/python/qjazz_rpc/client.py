"""gRPC Client test"""

import json
import os
import sys

from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from time import sleep, time
from typing import (
    Generator,
    Optional,
    TypeVar,
    overload,
)

import click
import grpc

from google.protobuf import json_format
from google.protobuf.message import Message
from grpc_health.v1 import (
    health_pb2,  # HealthCheckRequest
    health_pb2_grpc,  # HealthStub
)

from qjazz_contrib.core.config import TLSConfig
from qjazz_contrib.core.timer import Instant

from ._grpc import qjazz_pb2, qjazz_pb2_grpc

S = TypeVar("S")


@contextmanager
def channel(
    address: str,
    stub: type[S],
    ssl: Optional[TLSConfig] = None,
    channel_options: Optional[list] = None,
) -> Generator[S, None, None]:
    # Return a synchronous client channel
    # NOTE(gRPC Python Team): .close() is possible on a channel and should be
    # used in circumstances in which the with statement does not fit the needs
    # of the code.
    #
    # For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html
    def _read_if(f: Optional[Path]) -> Optional[bytes]:
        if f:
            with f.open("rb") as fp:
                return fp.read()
        else:
            return None

    with (
        grpc.secure_channel(
            address,
            grpc.ssl_channel_credentials(
                root_certificate=_read_if(ssl.cafile),
                certificate=_read_if(ssl.certfile),
                private_key=_read_if(ssl.keyfile),
            ),
            options=channel_options,
        )
        if ssl
        else grpc.insecure_channel(
            address,
            options=channel_options,
        )
    ) as chan:
        yield stub(chan)  # type: ignore [call-arg]


def MessageToJson(msg: Message) -> str:
    return json_format.MessageToJson(
        msg,
        # XXX Since protobuf 5.26
        # See https://github.com/python/typeshed/issues/11636
        always_print_fields_with_no_presence=True,  # type: ignore [call-arg]
    )


def MessageToDict(msg: Message) -> dict:
    return json_format.MessageToDict(
        msg,
        # XXX Since protobuf 5.26
        # See https://github.com/python/typeshed/issues/11636
        always_print_fields_with_no_presence=True,  # type: ignore [call-arg]
    )


@overload
def connect(
    stub: type[qjazz_pb2_grpc.QgisAdminStub] = qjazz_pb2_grpc.QgisAdminStub,
    exit_on_error: bool = True,
) -> AbstractContextManager[qjazz_pb2_grpc.QgisAdminStub]: ...


@overload
def connect(
    stub: type[qjazz_pb2_grpc.QgisServerStub],
    exit_on_error: bool = True,
) -> AbstractContextManager[qjazz_pb2_grpc.QgisServerStub]: ...


@contextmanager
def connect(stub=qjazz_pb2_grpc.QgisAdminStub, exit_on_error: bool = True) -> Generator:
    # NOTE(gRPC Python Team): .close() is possible on a channel and should be
    # used in circumstances in which the with statement does not fit the needs
    # of the code.
    #
    # For more channel options, please see https://grpc.io/grpc/core/group__grpc__arg__keys.html

    channel_options = [
        ("grpc.lb_policy_name", "round_robin"),
        ("grpc.enable_retries", 1),
        ("grpc.keepalive_timeout_ms", 10000),
    ]

    address = os.getenv("QGIS_GRPC_HOST", "localhost:23456")

    if os.getenv("CONF_GRPC_USE_TLS", "").lower() in (1, "yes", "true"):
        ssl = TLSConfig(
            keyfile=os.getenv("CONF_GRPC_TLS_KEYFILE"),
            certfile=os.getenv("CONF_GRPC_TLS_CERTFILE"),
            cafile=os.getenv("CONF_GRPC_TLS_CAFILE"),
        )
    else:
        ssl = None

    with channel(address, stub, ssl, channel_options) as _stub:
        try:
            yield _stub
        except grpc.RpcError as rpcerr:
            click.echo(f"RPC ERROR: {rpcerr.code()} {rpcerr.details()}", err=True)
            print_metadata(rpcerr.initial_metadata())
            print_metadata(rpcerr.trailing_metadata())
            if exit_on_error:
                sys.exit(1)


def print_metadata(metadata):
    status_code = ""
    for k, v in metadata:
        if k == "x-reply-status-code":
            status_code = v
        elif k.startswith("x-reply-header-"):
            h = k.replace("x-reply-header-", "", 1)
            click.echo(f"{h.title()} : {v}", err=True)
        elif k.startswith("x-"):
            click.echo(f"{k} : {v}", err=True)
    if status_code:
        click.echo(f"Return code: {status_code}", err=True)


@click.group("commands")
def cli_commands():
    """Send gRPC commands to the QGIS gRPC server

    \b
    Environment variables:
        QGIS_GRPC_HOST: address of the gRPC server - default  "localhost:23456"
        CONF_GRPC_USE_TLS: Use tls
        CONF_GRPC_TLS_KEYFILE: Path to TLS client  key file
        CONF_GRPC_TLS_CERTFILE: Path to TLS client certificat
        CONF_GRPC_TLS_CAFILE: Path no CA server certficatae
    """
    pass


@cli_commands.group("request")
def request_commands():
    """Send Qgis requests"""
    pass


@request_commands.command("ows")
@click.argument("project", nargs=1)
@click.option("--service", help="OWS service name", required=True)
@click.option("--request", help="OWS request name", required=True)
@click.option("--version", help="OWS service version")
@click.option("--param", "-p", multiple=True, help="Parameters KEY=VALUE")
@click.option("--headers", "-H", is_flag=True, help="Show headers")
@click.option("--url", help="Origin url")
@click.option(
    "--output",
    "-o",
    help="Destination file",
    type=click.Path(dir_okay=False),
)
def ows_request(
    project: str,
    service: str,
    request: str,
    version: Optional[str],
    param: list[str],
    headers: bool,
    output: Optional[str],
    url: Optional[str],
):
    """Send OWS request"""
    with connect(qjazz_pb2_grpc.QgisServerStub) as stub:
        t_start = time()
        stream = stub.ExecuteOwsRequest(
            qjazz_pb2.OwsRequest(
                service=service,
                request=request,
                target=project,
                url=url or "",
                options="&".join(param),
            ),
            timeout=10,
        )

        chunk = next(stream)
        t_end = time()

        fp = Path(output).open("w") if output else sys.stdout
        fp.buffer.write(chunk.chunk)
        for chunk in stream:
            fp.buffer.write(chunk.chunk)

        if headers:
            print_metadata(stream.initial_metadata())

        t_ms = int((t_end - t_start) * 1000.0)
        click.echo(f"First chunk returned in {t_ms} ms", err=True)


@request_commands.command("api")
@click.option("--name", help="Api name", required=True)
@click.option("--path", help="Api path", default="/")
@click.option("--target", help="Target project")
@click.option("--param", "-p", multiple=True, help="Parameters KEY=VALUE")
@click.option("--headers", "-H", is_flag=True, help="Show headers")
@click.option("--url", help="Origin url")
@click.option(
    "--output",
    "-o",
    help="Destination file",
    type=click.Path(dir_okay=False),
)
def api_request(
    name: str,
    path: str,
    target: Optional[str],
    param: list[str],
    headers: bool,
    output: Optional[str],
    url: Optional[str],
):
    """Send Api request"""
    with connect(qjazz_pb2_grpc.QgisServerStub) as stub:
        t_start = time()
        stream = stub.ExecuteApiRequest(
            qjazz_pb2.ApiRequest(
                name=name,
                path=path,
                method="GET",
                url=url or "",
                target=target,
                options="&".join(param),
            ),
            timeout=10,
        )

        chunk = next(stream)
        t_end = time()

        fp = Path(output).open("w") if output else sys.stdout
        fp.buffer.write(chunk.chunk)
        for chunk in stream:
            fp.buffer.write(chunk.chunk)

        if headers:
            print_metadata(stream.initial_metadata())

        t_ms = int((t_end - t_start) * 1000.0)
        click.echo(f"First chunk returned in {t_ms} ms", err=True)


#
# Cache
#


@cli_commands.group("cache")
def cache_commands():
    """Commands for cache management"""
    pass


@cache_commands.command("checkout")
@click.argument("project", nargs=1)
@click.option("--pull", is_flag=True, help="Load project in cache")
def checkout_project(project: str, pull: bool):
    """CheckoutProject PROJECT from cache

    If pull is true then the project is loaded into the cache as
    a pinned item.

    To remove a pinned item use the 'drop' cache command.
    """
    with connect() as stub:
        item = stub.CheckoutProject(
            qjazz_pb2.CheckoutRequest(uri=project, pull=pull),
        )
        click.echo(MessageToJson(item))


@cache_commands.command("drop")
@click.argument("project", nargs=1)
def drop_project(project: str):
    """Drop PROJECT from cache"""
    with connect() as stub:
        item = stub.DropProject(
            qjazz_pb2.DropRequest(uri=project),
        )
        click.echo(MessageToJson(item))


@cache_commands.command("clear")
def clear_cache():
    """Clear cache"""
    with connect() as stub:
        stub.ClearCache(
            qjazz_pb2.Empty(),
        )


@cache_commands.command("list")
def list_cache():
    """List projects from static (pinned) cache"""
    count = 0
    with connect() as stub:
        stream = stub.ListCache(qjazz_pb2.Empty())
        for item in stream:
            click.echo(MessageToJson(item))

    click.echo(f"Returned {count} items", err=True)


@cache_commands.command("update")
def update_cache():
    """Update cache item state"""
    count = 0
    with connect() as stub:
        stream = stub.UpdateCache(qjazz_pb2.Empty())
        for item in stream:
            click.echo(MessageToJson(item))

    click.echo(f"Returned {count} items", err=True)


@cache_commands.command("info")
@click.argument("project", nargs=1)
def project_info(project: str):
    """Return info from PROJECT in cache"""
    count = 0
    with connect() as stub:
        stream = stub.GetProjectInfo(
            qjazz_pb2.ProjectRequest(uri=project),
        )
        for item in stream:
            count += 1
            click.echo(MessageToJson(item))

    click.echo(f"Returned {count} items", err=True)


@cache_commands.command("catalog")
@click.option("--location", help="Select location")
def catalog(location: Optional[str]):
    """List available projects from search paths"""
    with connect() as stub:
        stream = stub.Catalog(
            qjazz_pb2.CatalogRequest(location=location),
        )
        count = 0
        for item in stream:
            count += 1
            click.echo(MessageToJson(item))

        click.echo(f"Returned {count} items", err=True)


@cache_commands.command("dump")
def dump_cache():
    """Dump cache and config for all backend workers

    Careful that this is a 'stop the world' method since it waits
    for all workers beeing availables and  should be called only for
    debugging purposes.
    """
    count = 0
    with connect() as stub:
        stream = stub.DumpCache(
            qjazz_pb2.Empty(),
        )
        for item in stream:
            count += 1
            item = MessageToDict(item)
            item["config"] = json.loads(item["config"])
            click.echo(json.dumps(item, indent=2))

    click.echo(f"Returned {count} items", err=True)


#
# Plugins
#


@cli_commands.group("plugin")
def plugin_commands():
    """Retrive Qgis plugin infos"""
    pass


@plugin_commands.command("list")
def list_plugins():
    """List plugins"""
    import json

    with connect() as stub:
        stream = stub.ListPlugins(
            qjazz_pb2.Empty(),
        )

        for item in stream:
            click.echo(
                json.dumps(
                    dict(
                        name=item.name,
                        path=item.path,
                        pluginType=item.plugin_type,
                        metadata=json.loads(item.metadata),
                    ),
                    indent=4,
                ),
            )


#
# Config
#


@cli_commands.group("config")
def config_commands():
    """Commands for configuration management"""
    pass


@config_commands.command("get")
def get_config():
    """Get server configuration"""
    with connect() as stub:
        resp = stub.GetConfig(qjazz_pb2.Empty())
        click.echo(resp.json)


@config_commands.command("set")
@click.argument("config", nargs=1)
def set_config(config: str):
    """Send CONFIG to remote"""
    with connect() as stub:
        if config.startswith("@"):
            config = Path(config[1:]).open().read()

        # Validate as json
        try:
            json.loads(config)
            stub.SetConfig(qjazz_pb2.JsonConfig(json=config))
        except json.JSONDecodeError as err:
            click.echo(err, err=True)


# Shortcut for settings log level only
@config_commands.command("log")
@click.argument("level", nargs=1)
def set_loglevel(level: str):
    """Send log level to remote"""
    with connect() as stub:
        stub.SetConfig(qjazz_pb2.JsonConfig(json=json.dumps({"logging": {"level": level}})))


#
#  status
#


@cli_commands.group("state")
def status_commands():
    """Commands for retrieving and setting rpc service state"""
    pass


@status_commands.command("env")
def get_status_env():
    """Get environment status"""
    with connect() as stub:
        resp = stub.GetEnv(qjazz_pb2.Empty())
        click.echo(resp.json)


@status_commands.command("disable")
def disable_server():
    """Disable server serving"""
    with connect() as stub:
        _ = stub.SetServerServingStatus(
            qjazz_pb2.ServerStatus(status=qjazz_pb2.ServingStatus.NOT_SERVING),
        )


@status_commands.command("enable")
def enable_server():
    """Enable server serving"""
    with connect() as stub:
        _ = stub.SetServerServingStatus(
            qjazz_pb2.ServerStatus(status=qjazz_pb2.ServingStatus.SERVING),
        )


@cli_commands.command("ping")
@click.option("--count", "-n", default=1, help="Number of requests to send")
@click.option("--server", is_flag=True, help="Ping qgis server service")
def ping(count: int, server: bool = False):
    """Ping service"""
    stub = qjazz_pb2_grpc.QgisServerStub if server else qjazz_pb2_grpc.QgisAdminStub
    target = "server" if server else "admin"
    with connect(stub) as stub:
        instant = Instant()
        for n in range(count):
            resp = stub.Ping(qjazz_pb2.PingRequest(echo=str(n)))
            elapsed = instant.elapsed_ms
            click.echo(
                f"({target}) seq={n:<5} resp={resp.echo:<5} time={elapsed} ms",
            )
            sleep(1)
            instant.restart()


@cli_commands.command("healthcheck")
@click.option("--watch", "-w", is_flag=True, help="Watch status changes")
@click.option("--set-error", is_flag=True, help="Exit with error if not serving")
def healthcheck_status(watch: bool, set_error: bool):
    """Check and monitor the status of a GRPC server"""
    with connect(stub=health_pb2_grpc.HealthStub, exit_on_error=not watch) as stub:
        ServingStatus = health_pb2.HealthCheckResponse.ServingStatus
        request = health_pb2.HealthCheckRequest(service="qjazz.QgisServer")
        if watch:
            for resp in stub.Watch(request):
                click.echo(f"=: {ServingStatus.Name(resp.status)}")
        else:
            resp = stub.Check(request)
            click.echo(f"=: {ServingStatus.Name(resp.status)}")

        if set_error and resp.status != ServingStatus.SERVING:
            sys.exit(1)


@cli_commands.command("stats")
@click.option("--watch", "-w", is_flag=True, help="Watch mode")
@click.option(
    "--interval",
    "-i",
    default=1,
    help="Interval in seconds in watch mode",
)
def display_stats(watch: bool, interval: int):
    """Return information about service processes"""
    with connect() as stub:
        resp = stub.Stats(qjazz_pb2.Empty())
        click.echo(MessageToJson(resp))
        if watch:
            sleep(interval)
            resp = stub.Stats(qjazz_pb2.Empty())
            click.echo(MessageToJson(resp))


@cli_commands.command("sleep")
@click.option("--delay", "-d", type=int, default=3, help="Response delay in seconds")
def sleep_request(delay: int):
    """Execute cancelable request"""
    # XXX The first request to an rpc worker is never cancelled
    # try to figure out why.
    with connect() as stub:
        resp = stub.Sleep.future(qjazz_pb2.SleepRequest(delay=delay))
        try:
            click.echo(MessageToJson(resp.result()))
        except KeyboardInterrupt:
            click.echo("Cancelling...", err=True)
            resp.cancel()


@cli_commands.command("reload")
def reload():
    """Reload QGIS processes"""
    with connect() as stub:
        stub.Reload(qjazz_pb2.Empty())


if __name__ == "__main__":
    cli_commands()
