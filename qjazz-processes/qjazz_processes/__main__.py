import sys

from pathlib import Path
from textwrap import indent, shorten
from typing import (
    Any,
    Optional,
    Protocol,
    Sequence,
    cast,
    get_args,
)

import click

from click import echo, style
from pydantic import JsonValue, TypeAdapter

from qjazz_contrib.core import config, manifest

from .schemas import JobStatusCode

PathType = click.Path(
    exists=True,
    readable=True,
    dir_okay=False,
    path_type=Path,
)


def error_exit(msg: str):
    click.echo(style(f"ERR: {msg}", fg="red"), err=True)
    sys.exit(1)


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

    from .executor import Executor, ExecutorConfig

    def executor_setup() -> Executor:
        class ConfigProto(Protocol):
            executor: ExecutorConfig

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
        return Executor(cast(ConfigProto, confservice.conf).executor)

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
@click.option("--json", "json_format", is_flag=True, help="Output json response")
@click.option("--long", "-l", "long_format", is_flag=True, help="Long format")
@click.pass_context
def list_services(ctx: click.Context, json_format: bool, long_format: bool):
    """List available services"""
    from pydantic import TypeAdapter

    from .executor import ServiceDict

    executor = ctx.obj.setup()
    services = executor.get_services()

    if json_format:
        resp = TypeAdapter(ServiceDict).dump_json(services, indent=4)
        echo(resp)
    elif long_format:
        for _, (_, s) in services.items():
            echo(style(f"{s.service:<15}", fg="green"), nl=False)
            echo(style(s.title, bold=True))
            echo(style(indent(s.description, "    "), italic=True))
    else:
        for _, (_, s) in services.items():
            echo(style(f"{s.service:<15}", fg="green"), nl=False)
            echo(style(f"{shorten(s.title, 20, placeholder='...'):<20}", bold=True), nl=False)
            echo(style(shorten(s.description, 50, placeholder="..."), italic=True))


@control.command("reload")
@click.option("--service", "-S", required=True, envvar="QJAZZ_SERVICE")
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
@click.option("--service", "-S", required=True, envvar="QJAZZ_SERVICE")
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
@click.option("--service", "-S", required=True, envvar="QJAZZ_SERVICE")
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


@main.group("process")
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
@click.option("--service", "-S", required=True, envvar="QJAZZ_SERVICE")
@click.option("--json", "json_format", is_flag=True, help="Output json response")
@click.pass_context
def list_processes(ctx: click.Context, service: str, json_format: bool):
    """List processes"""
    from typing import Sequence

    from pydantic import TypeAdapter

    from .executor import ProcessSummary, ServiceNotAvailable

    executor = ctx.obj.setup()
    executor.update_services()

    try:
        processes = executor.processes(service)
        if json_format:
            resp = TypeAdapter(Sequence[ProcessSummary]).dump_json(
                processes,
                by_alias=True,
                indent=4,
            )
            click.echo(resp)
        else:
            echo(style("P = Require project, D = Deprecated, I = Known Issues"))
            for p in processes:
                md = {m.role: m.value for m in p.metadata}
                bD = "D" if md.get("Deprecated") else " "
                bI = "I" if md.get("KnownIssues") else " "
                bP = "P" if md.get("RequiresProject") else " "
                echo(style(f" {bD}{bP}{bI} ", fg="yellow"), nl=False)
                echo(style(f"{p.id_:<45}", fg="green"), nl=False)
                echo(style(shorten(p.title, 50, placeholder="..."), bold=True))
                if p.description:
                    echo(style(indent(p.description, "    "), italic=True))

    except ServiceNotAvailable:
        error_exit("Service not available")


@processes.command("describe")
@click.argument("ident")
@click.option("--service", "-S", required=True, envvar="QJAZZ_SERVICE")
@click.option("--project", help="Project name")
@click.option("--json", "json_format", is_flag=True, help="Output json response")
@click.pass_context
def describe_process(
    ctx: click.Context,
    service: str,
    ident: str,
    project: Optional[str],
    json_format: bool,
):
    """Describe processes"""
    from pydantic import TypeAdapter

    from .executor import ProcessDescription, ServiceNotAvailable
    from .schemas import InputDescription

    executor = ctx.obj.setup()
    executor.update_services()

    try:
        processes = executor.describe(service, ident, project=project)
        if processes is None:
            error_exit(f"Process '{ident}' not found for service '{service}'")

        if json_format:
            resp = TypeAdapter(ProcessDescription).dump_json(
                processes,
                by_alias=True,
                indent=4,
            )
            click.echo(resp)
        else:
            p = processes
            md = {m.role: m.value for m in p.metadata}

            flags = ", ".join(
                f
                for f in (
                    "Deprecated" if md.get("Deprecated") else "",
                    "Known issues" if md.get("KnownIssues") else "",
                    "Requires project" if md.get("RequiresProject") else "",
                )
                if f
            )

            echo()
            echo(style(p.id_, bold=True), nl=False)
            echo(f" [{flags}]") if flags else echo()
            echo(f" -- {p.title}")
            if p.description:
                echo(style(indent(p.description, "    "), italic=True))

            def get_type(schema):  # -> Optional[str]:
                return schema.get("format") or schema.get("contentMediaType") or schema.get("type")

            def format_type(schema):  # -> str:
                if schema.get("oneOf"):
                    one_of = schema["oneOf"]
                    fmt = "|".join(get_type(t) for t in one_of if t)  # type: ignore [misc]
                    fmt = f"({fmt})"
                elif schema.get("type"):
                    match schema["type"]:
                        case "array":
                            fmt = f"[{schema['items'].get('type') or '...'}]"
                        case other:
                            fmt = other
                else:
                    fmt = "..."
                return fmt

            def format_description(name: str, inp: InputDescription):
                schema = inp.schema_
                echo(click.style(f"  {name:<15} ", bold=True), nl=False)
                fmt = format_type(schema)
                echo(f"{fmt:<15} {inp.title}", nl=False)
                default = schema.get("default")
                if default:
                    echo(f" --  default:  {default}", nl=False)
                echo()
                description = inp.description
                if description:
                    for line in description.split("\n"):
                        echo(click.style(f"    {line:}", italic=True))

            #
            # Format inputs
            #
            echo("\nInputs:")
            for name, inp in p.inputs.items():
                format_description(name, inp)
            #
            # Format outputs
            #
            echo("\nOutputs:")
            for name, outp in p.outputs.items():
                format_description(name, outp)

            echo()

    except ServiceNotAvailable:
        error_exit("Service not available")


@processes.command("execute")
@click.argument("ident")
@click.argument("inputs", nargs=-1, type=click.UNPROCESSED)
@click.option("--service", "-S", required=True, envvar="QJAZZ_SERVICE")
@click.option("--project", help="Project name")
@click.option("--tag")
@click.option("--realm")
@click.option("--timeout", type=int)
@click.option("--priority", type=int, default=0, help="Job priority")
@click.option("--nowait", is_flag=True, help="Do not wait for result")
@click.option("--outputs", help="Job output specification")
@click.pass_context
def execute_process(
    ctx: click.Context,
    ident: str,
    inputs: Sequence[str],
    service: str,
    project: Optional[str],
    tag: Optional[str],
    realm: Optional[str],
    timeout: Optional[int],
    priority: int,
    nowait: bool,
    outputs: Optional[str],
):
    """Execute process IDENT

    Parameters are <key>=<value> pair

    If inputs is '-', inputs data are in Json format
    from standard input
    """
    from pydantic import TypeAdapter

    from .executor import ServiceNotAvailable
    from .schemas import JobExecute, JobResults, JsonDict, Output

    executor = ctx.obj.setup()
    executor.update_services()

    OutputDict = dict[str, Output]

    inps: JsonDict
    outs: OutputDict

    if inputs and inputs[0] == "-":
        inps = TypeAdapter(JsonDict).validate_json("".join(line for line in sys.stdin))
    else:
        # Parse kv arguments
        def kv(s: str) -> tuple[str, JsonValue]:
            t = s.split('=', maxsplit=1)
            if len(t) !=2:
                error_exit("Missing value for {s}")
            value: Any = t[1]
            if value.startswith("["):
                if not value.endswith("]"):
                    error_exit(f"Missing ']' for {t[0]}")
                value = value[1:-1].split(",")
            elif value.startswith("{"):
                try:
                    value = TypeAdapter(JsonValue).validate_json(value)
                except Exception as err:
                    error_exit(f"{err}")

            return (t[0], value)

        inps = dict(kv(inp) for inp in inputs)

    if outputs:
        outs = TypeAdapter(OutputDict).validate_json(outputs)
    else:
        outs = {}

    try:
        result = executor.execute(
            service,
            ident,
            request=JobExecute(
                inputs=inps,
                outputs=outs,
            ),
            project=project,
            context={},
            realm=realm,
            # Set the pending timeout to the wait preference
            pending_timeout=timeout,
            tag=tag,
            priority=priority,
        )

        if not nowait:
            try:
                job_results = result.get(timeout)
            except Exception as err:
                error_exit(f"{err}: {result.status().model_dump_json()}")

            out = TypeAdapter(JobResults).dump_json(
                job_results,
                by_alias=True,
                exclude_none=True,
            ).decode()
        else:
            out = result.status().model_dump_json()

        click.echo(out)

    except ServiceNotAvailable:
        error_exit("Service not available")

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
@click.option("--service", help="Filter by service", envvar="QJAZZ_SERVICE")
@click.option("--realm", help="Filter by realm")
@click.option("--json", "json_format", is_flag=True, help="Output json response")
@click.option("-s", "--short", is_flag=True, help="Short display")
@click.option("-l", "--limit", type=int, help="Page size", default=25)
@click.option("--index", type=int, help="Start index", default=0)
@click.option(
    "--status",
    "filter_status",
    help="Status filter",
    multiple=True,
    type=click.Choice(get_args(JobStatusCode)),
)
@click.option("--tags", "filter_tags", help="tags filter", multiple=True)
@click.pass_context
def list_jobs(
    ctx: click.Context,
    service: Optional[str],
    realm: Optional[str],
    json_format: bool,
    short: bool,
    limit: int,
    index: int,
    filter_status: Sequence[str],
    filter_tags: Sequence[str],
):
    """List jobs"""

    from .executor import JobStatus

    executor = ctx.obj.setup()
    executor.update_services()

    if not json_format:
        if service:
            echo(style(f"\nJobs for service {service}:\n", bold=True))
        else:
            echo(style("\nJobs for all services\n", bold=True))

    has_next = True

    def pred(job: JobStatus) -> bool:
        return (not filter_tags or job.tag in filter_tags) and (not filter_status or job.status in filter_status)

    while has_next:
        jobs = executor.jobs(service, realm=realm, limit=limit, cursor=index, with_details=True)
        has_next = len(jobs) >= limit

        filtered_jobs = filter(pred, jobs)

        if json_format:
            for job in filtered_jobs:
                resp = job.model_dump_json(indent=4)
                click.echo(resp)
        else:

            def status_color(status: str) -> str | None:
                col: str | None
                match status:
                    case "failed":
                        col = "red"
                    case "successful":
                        col = "green"
                    case "started":
                        col = "yellow"
                    case _:
                        col = None
                return col

            if short:
                for i, p in enumerate(filtered_jobs):
                    status = p.status
                    fg = status_color(status)
                    bS = "S" if p.run_config and p.run_config.get("subscriber") else " "
                    echo(f"{bS} ", nl=False)
                    echo(f"{i + index + 1:>4} ", nl=False)
                    echo(style(f"{p.job_id:<40}", fg=fg), nl=False)
                    echo(style(f"{p.process_id:<40}", fg="blue"), nl=False)
                    echo(style(f"{status[:4].upper()} ", fg=fg, bold=True))
                    if p.tag:
                        echo(style(f"       \u2b11 {p.tag}", italic=True))
            else:
                for p in filtered_jobs:
                    for k, v in p.model_dump(mode="json", by_alias=True).items():
                        if k == "links":
                            continue
                        echo(f"{style(k, fg='blue'):<25}{style(v, fg='green')}")
                    echo("-----------------------------------------------")

        if has_next:
            try:
                input("Press Enter to continue...")
                index += limit
            except EOFError:
                break


@jobs.command("status")
@click.argument("job_id")
@click.option("--json", "json_format", is_flag=True, help="Output json response")
@click.pass_context
def jobs_status(ctx: click.Context, job_id: str, json_format: bool):
    """Display job status"""

    executor = ctx.obj.setup()

    job = executor.job_status(job_id, with_details=True)
    if not job:
        echo("No job", err=True)
        return

    if json_format:
        echo(job.model_dump_json(indent=4))
    else:
        echo("\n")
        echo(style(f"Job {job_id}", bold=True))
        for name, output in job.model_dump(mode="json", by_alias=True, exclude_none=True).items():
            echo(click.style(f"  {name:<15}", bold=True), nl=False)
            match output:
                case list():
                    echo(style(dump_json(output), fg="green"))
                case dict():
                    echo()
                    for k, v in output.items():
                        echo(f"    {style(k, fg='blue')}: {style(dump_json(v), fg='green')}")
                case _:
                    echo(style(output, fg="green"))


#
@jobs.command("results")
@click.argument("job_id")
@click.option("--json", "json_format", is_flag=True, help="Output json response")
@click.pass_context
def jobs_results(ctx: click.Context, job_id: str, json_format: bool):
    """Display job results"""

    executor = ctx.obj.setup()

    results = executor.job_results(job_id)
    if not results:
        echo("No results", err=True)
        return

    if json_format:
        echo(dump_json(results))
    else:
        echo("\n")
        echo(style(f"Job {job_id}", bold=True))
        for name, output in results.items():
            echo(click.style(f"  {name:<15}", bold=True), nl=False)
            match output:
                case list():
                    echo(style(dump_json(output), fg="green"))
                case dict():
                    echo()
                    for k, v in output.items():
                        echo(f"    {style(k, fg='blue')}: {style(dump_json(v), fg='green')}")
                case _:
                    echo(style(output, fg="green"))


def dump_json(v):
    v = (
        TypeAdapter(JsonValue)
        .dump_json(
            v,
            exclude_none=True,
            indent=4,
        )
        .decode()
    )
    return indent(v, "    ").lstrip()


main()
