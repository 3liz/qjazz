""" Command line client
    For running processinc algorithms
"""
import sys

from pathlib import Path
from types import SimpleNamespace

import click

from click import echo, style
from pydantic import (
    JsonValue,
    TypeAdapter,
)
from typing_extensions import (
    Any,
    Optional,
)

from qgis.core import QgsProcessingFeedback, QgsProject

from py_qgis_contrib.core import config, logger, qgis

from .config import ProcessingConfig

if sys.version_info >= (3, 11):
    import tomllib as toml
else:
    import tomli as toml   # noqa F401


def load_configuration(
    configpath: Optional[Path],
    verbose: bool = False,
) -> config.Config:
    if configpath:
        cnf = config.read_config_toml(
            configpath,
            location=str(configpath.parent.absolute()),
        )
    else:
        cnf = {}

    config.confservice.validate(cnf)
    logger.setup_log_handler(logger.LogLevel.TRACE if verbose else logger.LogLevel.ERROR)

    return config.confservice.conf


def init_qgis(
    processing_config: ProcessingConfig,
    use_projects: bool = True,
) -> qgis.QgisPluginService:
    #
    # Initalize Qgis
    #

    qgis.init_qgis_application(settings=processing_config.settings())
    qgis.init_qgis_processing()

    plugin_service = qgis.QgisPluginService(processing_config.plugins)
    plugin_service.load_plugins(qgis.PluginType.PROCESSING, None)
    plugin_service.register_as_service()

    if use_projects:
        from py_qgis_cache import CacheManager

        CacheManager.initialize_handlers()

        cm = CacheManager(processing_config.projects)
        cm.register_as_service()

    return plugin_service


def get_project(path: str) -> QgsProject:
    from py_qgis_cache import CacheManager
    from py_qgis_cache import CheckoutStatus as Co

    cm = CacheManager.get_service()

    # Resolve location
    url = cm.resolve_path(path)
    # Check status
    md, status = cm.checkout(url)
    match status:
        case Co.REMOVED | Co.NOTFOUND:
            raise FileNotFoundError(f"Project {url} not found")
        case _:
            entry, _ = cm.update(md, status)  # type: ignore [arg-type]
            project = entry.project
    return project


FilePathType = click.Path(
    exists=True,
    readable=True,
    dir_okay=False,
    path_type=Path,
)


@click.group()
@click.option(
    "--config", "-C", "configpath",
    help="Path to configuration file",
    type=FilePathType,
    envvar="PY_QGIS_PROCESSES_CONFIG",
)
@click.option("--verbose", "-v", is_flag=True, help="Set verbose output")
@click.pass_context
def cli_commands(
    ctx: click.Context,
    configpath: Optional[Path],
    verbose: bool = False,
):
    ctx.obj = SimpleNamespace(
        configpath=configpath,
        verbose=verbose,
    )


@cli_commands.command('config')
@click.option("--schema", is_flag=True, help="Print configuration schema")
@click.option(
    "--format", "out_format",
    type=click.Choice(("json", "yaml", "toml")),
    default="json",
    help="Output format (schema only)",
)
@click.pass_context
def dump_config(
    ctx: click.Context,
    out_format: str,
    schema: bool = False,
):
    """ Display configuration
    """
    if schema:
        match out_format:
            case 'json':
                json_schema = config.confservice.json_schema()
                echo(TypeAdapter(JsonValue).dump_json(json_schema, indent=4))
            case 'yaml':
                from ruamel.yaml import YAML
                json_schema = config.confservice.json_schema()
                yaml = YAML()
                yaml.dump(json_schema, sys.stdout)
            case 'toml':
                config.confservice.dump_toml_schema(sys.stdout)
    else:
        conf = load_configuration(ctx.obj.configpath)
        echo(conf.model_dump_json(indent=4))


#
# Plugins
#

@cli_commands.command("plugins")
@click.pass_context
def processing_plugins(
    ctx: click.Context,
):
    """ List loaded plugins
    """
    conf: Any = load_configuration(ctx.obj.configpath)
    plugins = init_qgis(conf.processing, use_projects=False)

    for p in plugins.plugins:
        md: Any = p.metadata
        echo(style(f"* {p.name:<20}", bold=True), nl=False)
        echo(f"{md['general'].get('version', 'n/a'):<10}", nl=False)
        echo(f"{md['general'].get('qgisminimumversion', 'n/a'):<10}", nl=False)
        echo(p.path)

#
# Processes
#


@cli_commands.group('processes')
def processes_commands():
    """ Processes commands
    """
    pass


@processes_commands.command("list")
@click.option("--json", "json_format", is_flag=True, help="Output as json response")
@click.option("--provider", "-p", help="Select provider")
@click.option(
    "--include-deprecated", "deprecated",
    is_flag=True,
    help="Include deprecated algorithms",
)
@click.pass_context
def list_processes(
    ctx: click.Context,
    json_format: bool,
    provider: str,
    deprecated: bool,
):
    """ List processes
    """
    from .processes import ProcessAlgorithm

    conf: Any = load_configuration(ctx.obj.configpath)
    init_qgis(conf.processing)

    algs = ProcessAlgorithm.algorithms(
        include_deprecated=deprecated,
        providers=(provider,) if provider else (),
    )

    if json_format:
        from py_qgis_processes_schemas import ProcessSummaryList
        body = ProcessSummaryList.dump_json(
            [alg.summary() for alg in algs],
            by_alias=True,
            exclude_none=True,
        )
        click.echo(body)
    else:
        for alg in algs:
            s = alg.summary()
            bD = 'D' if alg.deprecated else ' '
            bP = 'P' if alg.require_project else ' '
            bI = 'I' if alg.known_issues else ' '
            echo(style(f" {bD}{bP}{bI} ", fg='yellow'), nl=False)
            echo(style(f"{s.id_:<40}", fg='green'), nl=False)
            echo(style(f"{s.title:<20}", bold=True), nl=False)
            echo(style(f"{s.description:<30}", italic=True), nl=False)
            echo()


@processes_commands.command("describe")
@click.argument("ident")
@click.option("--project", "project_path", help="Path to project")
@click.pass_context
def describe_processes(
    ctx: click.Context,
    ident: str,
    project_path: str,
):
    """ Describe process IDENT
    """
    from .processes import ProcessAlgorithm

    conf: Any = load_configuration(ctx.obj.configpath)
    init_qgis(conf.processing)

    alg = ProcessAlgorithm.find_algorithm(ident)
    if alg is None:
        echo(style(f"Algorithm '{ident}' not found", fg="red"))
        ctx.abort()

    project = get_project(project_path) if project_path else None

    d = alg.description(project)
    click.echo(d.model_dump_json())


@processes_commands.command("execute")
@click.argument("inputs")
@click.option("--ident", help="Processe ID", required=True)
@click.option("--project", "project_path", help="Path to project")
@click.option("--force-yaml", is_flag=True, help="Force inputs as Yam")
@click.option("--dry-run", is_flag=True, help="Dry run")
@click.pass_context
def execute_processes(
    ctx: click.Context,
    inputs: str,
    ident: str,
    project_path: str,
    force_yaml: bool,
    dry_run: bool,
):
    """ Execute process
    """
    from py_qgis_processes_schemas import JobExecute, JsonDict

    from .processes import (
        ProcessAlgorithm,
        ProcessingContext,
    )

    # Read inputs
    if inputs.startswith('@'):
        # File inputs
        path = Path(inputs[1:])
        if not path.exists():
            echo(style(f"{path} not found", fg='red'))
            ctx.abort()

        if force_yaml or path.suffix in ('.yml', '.yaml'):
            from ruamel.yaml import YAML
            request = JobExecute.model_validate(YAML().load(path))
        else:
            with Path(inputs[1:]).open() as f:
                request = JobExecute.model_validate_json(f.read())
    else:
        if inputs == '-':
            # Read from standard input
            import fileinput

            from io import StringIO
            s = StringIO()
            for line in fileinput.input():
                s.write(line)
            inputs = s.getvalue()

        inputs = inputs.strip(' ')
        if inputs.startswith('{') and not force_yaml:
            request = JobExecute.model_validate_json(inputs)
        else:
            from ruamel.yaml import YAML
            request = JobExecute.model_validate(YAML().load(StringIO(inputs)))

    conf: Any = load_configuration(ctx.obj.configpath)
    init_qgis(conf.processing)

    alg = ProcessAlgorithm.find_algorithm(ident)
    if alg is None:
        echo(style(f"Algorithm '{ident}' not found", fg="red"))
        ctx.abort()

    project = get_project(project_path) if project_path else None

    feedback = FeedBack()
    context = ProcessingContext(conf.processing)
    context.feedback = feedback

    # Set workdir

    if project:
        context.setProject(project)
    elif alg.require_project:
        echo(style("Algorithm require project", fg='red'))
        ctx.abort()

    if dry_run:
        echo(style("Dry run, not executing process", fg='yellow'))
        echo("Request is:")
        echo(request.model_dump_json(indent=4))

        alg.validate_execute_parameters(request, feedback, context)

        return

    if not ctx.obj.verbose:
        logger.set_log_level(logger.LogLevel.INFO)

    results = alg.execute(request, feedback, context)
    echo(TypeAdapter(JsonDict).dump_json(results, indent=4))


class FeedBack(QgsProcessingFeedback):

    def __init__(self):
        super().__init__(False)

    def pushFormattedMessage(html: str, text: str):
        logger.info(text)

    def setProgressText(self, message: str):
        logger.info("Progress: %s", message)

    def reportError(self, error: str, fatalError: bool = False):
        (logger.critical if fatalError else logger.error)(error)

    def pushInfo(self, info: str) -> None:
        logger.info(info)

    def pushWarning(self, warning: str) -> None:
        logger.warning(warning)

    def pushDebugInfo(self, info: str) -> None:
        logger.debug(info)


def main():
    cli_commands()
