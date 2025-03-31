
from pathlib import Path
from typing import Optional, cast

import click

PathType = click.Path(
    exists=True,
    readable=True,
    dir_okay=False,
    path_type=Path,
)


@click.group()
def main():
    pass


#
# Server
#

@main.command("serve")
@click.option(
    "--conf",
    "-C",
    "configpath",
    type=PathType,
    help="Path to configuration file",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose mode (trace)")
def run_server(
    configpath: Path,
    verbose: bool,
):
    """Start server"""
    from qjazz_contrib.core import logger

    from .server import load_configuration, serve

    conf = load_configuration(configpath)
    logger.setup_log_handler(
        logger.LogLevel.TRACE if verbose else conf.logging.level,
    )

    serve(conf)


#
#  Service commands
#

@main.group("service")
@click.option(
    "--conf",
    "-C",
    "configpath",
    type=PathType,
    help="Path to configuration file",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose mode (trace)")
@click.pass_context
def control(ctx: click.Context, configpath: Optional[Path], verbose: bool):
    """Service commands"""
    from types import SimpleNamespace

    from qjazz_contrib.core import config, logger
    from qjazz_processes.executor import Executor, ExecutorConfig

    def control_setup() -> Executor:
        logger.set_log_level(
            logger.LogLevel.DEBUG if verbose else logger.LogLevel.ERROR,
        )
        confservice = config.ConfBuilder()
        confservice.add_section("executor", ExecutorConfig)
        if configpath:
            cnf = config.read_config_toml(configpath)
        else:
            cnf = {}
        confservice.validate(cnf)
        if verbose:
            click.echo(confservice.conf)
        return Executor(cast(ExecutorConfig, confservice.conf.executor))

    ctx.obj = SimpleNamespace(
        configpath=configpath,
        verbose=verbose,
        setup=control_setup,
    )


@control.command("ls")
@click.pass_context
def list_services(ctx: click.Context):
    """List available services"""
    from pydantic import TypeAdapter

    from qjazz_processes.executor import ServiceDict

    executor = ctx.obj.setup()
    services = executor.get_services()

    resp = TypeAdapter(ServiceDict).dump_json(services, indent=4)
    click.echo(resp)


@control.command("reload")
@click.argument("service")
@click.pass_context
def reload_service(ctx: click.Context, service: str):
    """Reload worker pool for SERVICE"""
    from pydantic import JsonValue, TypeAdapter

    executor = ctx.obj.setup()
    executor.update_services()
    result = executor.restart_pool(service)

    resp = TypeAdapter(JsonValue).dump_json(result, indent=4)
    click.echo(resp)


@control.command("shutdown")
@click.argument("service")
@click.pass_context
def shutdown_service(ctx: click.Context, service: str):
    """Shutdown service"""
    from pydantic import JsonValue, TypeAdapter

    executor = ctx.obj.setup()
    executor.update_services()
    result = executor.shutdown(service)

    resp = TypeAdapter(JsonValue).dump_json(result, indent=4)
    click.echo(resp)


@control.command("ping")
@click.argument("service")
@click.option("--repeat", "-n", type=int, default=0, help="Ping every <repeat> seconds")
@click.pass_context
def ping_service(ctx: click.Context, service: str, repeat: int):
    """Ping service"""
    from pydantic import JsonValue, TypeAdapter

    executor = ctx.obj.setup()
    executor.update_services()

    def _ping():
        result = executor.ping(service)
        resp = TypeAdapter(JsonValue).dump_json(result, indent=4)
        click.echo(resp)

    if repeat > 0:
        from time import sleep

        while True:
            _ping()
            sleep(repeat)
    else:
        _ping()


main()
