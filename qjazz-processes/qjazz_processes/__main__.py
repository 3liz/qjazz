import sys

from pathlib import Path
from typing import Optional, cast

import click

from qjazz_contrib.core import config, manifest

PathType = click.Path(
    exists=True,
    readable=True,
    dir_okay=False,
    path_type=Path,
)


@click.group()
@click.version_option(
    package_name="qjazz-processes",
    message=f"Qjazz version: %(version)s ({manifest.short_commit_id() or 'n/a'})",
)
@click.option(
    "--env-settings",
    type=click.Choice(("disabled", "last", "first")),
    default="first",
    help="Environment variables precedence",
    show_default=True,
)
def main(env_settings: config.EnvSettingsOption):
    config.set_env_settings_option(env_settings)


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
@click.option("--dump-config", is_flag=True, help="Dump config and exit")
def run_server(configpath: Path, verbose: bool, dump_config: bool):
    """Start server"""
    from qjazz_contrib.core import logger

    from .server import load_configuration, serve

    conf = load_configuration(configpath)
    if dump_config:
        click.echo(conf.model_dump_json(indent=4))
        return

    logger.setup_log_handler(
        logger.LogLevel.TRACE if verbose else conf.logging.level,
    )

    serve(conf)


#


def setup_executor_context(
    ctx: click.Context,
    configpath: Optional[Path],
    verbose: bool,
):
    from types import SimpleNamespace

    from qjazz_contrib.core import config, logger
    from qjazz_processes.executor import Executor, ExecutorConfig

    def executor_setup() -> Executor:
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
        setup=executor_setup,
    )


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
def control(
    ctx: click.Context,
    configpath: Optional[Path],
    verbose: bool,
):
    """Service commands"""
    setup_executor_context(ctx, configpath, verbose)


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
@click.option(
    "--repeat",
    "-n",
    type=int,
    default=0,
    help="Ping every <REPEAT> seconds",
    metavar="REPEAT",
)
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


#
#  Processes commands
#


@main.group("processes")
@click.option(
    "--conf",
    "-C",
    "configpath",
    type=PathType,
    help="Path to configuration file",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose mode (trace)")
@click.pass_context
def processes(
    ctx: click.Context,
    configpath: Optional[Path],
    verbose: bool,
):
    """Processes commands"""
    setup_executor_context(ctx, configpath, verbose)


@processes.command("ls")
@click.argument("service")
@click.pass_context
def list_processes(ctx: click.Context, service: str):
    """List processes"""
    from typing import Sequence

    from pydantic import TypeAdapter

    from .executor import ProcessSummary, ServiceNotAvailable

    executor = ctx.obj.setup()
    executor.update_services()

    try:
        processes = executor.processes(service)
        resp = TypeAdapter(Sequence[ProcessSummary]).dump_json(
            processes,
            by_alias=True,
            indent=4,
        )
        click.echo(resp)
    except ServiceNotAvailable:
        click.echo("Service not available", err=True)
        sys.exit(1)


@processes.command("describe")
@click.argument("service")
@click.argument("ident")
@click.option("--project", help="Project name")
@click.pass_context
def describe_processes(ctx: click.Context, service: str, ident: str, project: Optional[str]):
    """Describe processes"""
    from pydantic import TypeAdapter

    from .executor import ProcessDescription, ServiceNotAvailable

    executor = ctx.obj.setup()
    executor.update_services()

    try:
        processes = executor.describe(service, ident, project=project)
        resp = TypeAdapter(ProcessDescription).dump_json(
            processes,
            by_alias=True,
            indent=4,
        )
        click.echo(resp)
    except ServiceNotAvailable:
        click.echo("Service not available", err=True)
        sys.exit(1)


#
# Jobs
#


@main.group("jobs")
@click.option(
    "--conf",
    "-C",
    "configpath",
    type=PathType,
    help="Path to configuration file",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose mode (trace)")
@click.pass_context
def jobs(
    ctx: click.Context,
    configpath: Optional[Path],
    verbose: bool,
):
    """Jobs commands"""
    setup_executor_context(ctx, configpath, verbose)


@jobs.command("ls")
@click.option("--service", help="Filter by service")
@click.option("--realm", help="Filter by realm")
@click.pass_context
def list_jobs(
    ctx: click.Context,
    service: Optional[str],
    realm: Optional[str],
):
    """List jobs"""
    from typing import Sequence

    from pydantic import TypeAdapter

    from .executor import JobStatus, ServiceNotAvailable

    executor = ctx.obj.setup()
    executor.update_services()

    try:
        jobs = executor.jobs(service, realm=realm)
        resp = TypeAdapter(Sequence[JobStatus]).dump_json(
            jobs,
            by_alias=True,
            indent=4,
        )
        click.echo(resp)
    except ServiceNotAvailable:
        click.echo("Service not available", err=True)
        sys.exit(1)


#

main()
