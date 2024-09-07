""" QGIS gRCP CLI administration
"""
import asyncio
import json
import sys

from functools import wraps
from pathlib import Path

import click

from typing_extensions import Any, List, Optional

from py_qgis_contrib.core import config, logger

from .config import ConfigProto, confservice
from .service import PoolClient, ResolverConfig, Service

FilePathType = click.Path(
    exists=True,
    readable=True,
    dir_okay=False,
    path_type=Path,
)


def load_configuration(configpath: Optional[Path], verbose: bool = False) -> ConfigProto:
    if configpath:
        cnf = config.read_config_toml(
            configpath,
            location=str(configpath.parent.absolute()),
        )
    else:
        cnf = {}
    try:
        confservice.validate(cnf)
        # Load external configuration if requested
        asyncio.run(confservice.conf.config_url.load_configuration())
        if verbose:
            click.echo(confservice.conf.model_dump_json(indent=4))
    except config.ConfigError as err:
        click.echo(f"Configuration error: {err}")
        sys.exit(1)

    conf = confservice.conf

    logger.setup_log_handler(logger.LogLevel.TRACE if verbose else conf.logging.level)

    return confservice.conf


def get_pool(conf: ResolverConfig, name: str) -> Optional[PoolClient]:
    """ Create a pool client from config
    """
    for resolver in conf.get_resolvers():
        if resolver.label == name or resolver.address == name:
            return PoolClient(resolver)

    # No match in config, try to resolve it
    # directly from addresse
    return PoolClient(ResolverConfig.from_string(name))


# Workaround https://github.com/pallets/click/issues/295
def global_options():
    def _wrapper(f):
        @wraps(f)
        @click.option("--verbose", "-v", is_flag=True, help="Set verbose mode")
        @click.option(
            "--conf", "-C", "configpath",
            envvar="QGIS_GRPC_ADMIN_CONFIGFILE",
            help="configuration file",
            type=FilePathType,
        )
        def _inner(*args, **kwargs):
            return f(*args, **kwargs)
        return _inner
    return _wrapper


@click.group()
def cli_commands():
    pass


def print_pool_status(pool, statuses):
    statuses = dict(statuses)
    click.echo(f"{pool.label:<15}{pool.address:<15} backends: {len(pool)}")
    for i, s in enumerate(pool.backends):
        status = "ok" if statuses[s.address] else "unavailable"
        click.echo(f"{i + 1:>2}. {s.address:<20} {status}")

#
# Watch
#


@cli_commands.command('watch')
@click.option("--host", help="Watch specific hostname")
@global_options()
def watch(verbose: bool, host: Optional[str], configpath: Optional[Path]):
    """ Watch a cluster of qgis gRPC services
    """
    conf = load_configuration(configpath, verbose)
    if host:
        async def _watch1(pool):
            await pool.update_backends()
            async for statuses in pool.watch():
                print_pool_status(pool, statuses)

        pool = get_pool(conf.resolvers, host)
        if pool is not None:
            asyncio.run(_watch1(pool))
        else:
            click.echo(f"ERROR: {host} not found", file=sys.stderr)
    else:
        service = Service(conf.resolvers)
        if not service.num_pools():
            click.echo("No servers", file=sys.stderr)
            return

        async def _watch0():
            await service.synchronize()
            async for pool, statuses in service.watch():
                print_pool_status(pool, statuses)

        asyncio.run(_watch0())


#
# Stats
#

@cli_commands.command('pools')
@global_options()
def list_pools(verbose: bool, configpath: Optional[Path]):
    """ List all pools
    """
    conf: Any = load_configuration(configpath, verbose)
    service = Service(conf.resolvers)
    if not service.num_pools():
        click.echo("No servers", file=sys.stderr)
        return

    async def _display():
        await service.synchronize()
        for n, pool in enumerate(service.pools):
            click.echo(f"Pool {n + 1:>2}. {pool.label:<15}{pool.address:<15} backends: {len(pool)}")
            for s in pool.backends:
                click.echo(f" * {s.address}")

    asyncio.run(_display())


@cli_commands.command('stats')
@click.option("--host", help="Watch specific hostname", required=True)
@click.option("--watch", is_flag=True, help="Check periodically")
@click.option("--interval", help="Check interval (seconds)", default=3)
@global_options()
def stats(verbose: bool, host: str, watch: bool, interval: int, configpath: Optional[Path]):
    """ Output  qgis gRPC services stats
    """
    conf: Any = load_configuration(configpath, verbose)

    if watch:
        async def _watch(pool):
            await pool.update_backends()
            async for stats in pool.watch_stats(interval):
                click.echo(json.dumps([r for _, r in stats], indent=4, sort_keys=True))

    else:
        async def _watch(pool):
            await pool.update_backends()
            stats = await pool.stats()
            click.echo(json.dumps([r for _, r in stats], indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_watch(pool))
    else:
        click.echo(f"ERROR: {host} not found", file=sys.stderr)

#
# Configuration
#


@cli_commands.group('conf')
def conf_commands():
    """  Configuration management
    """
    pass


@conf_commands.command('get')
@click.option("--format", "indent", is_flag=True, help="Display formatted")
@click.option("--host", help="Watch specific hostname", required=True)
@global_options()
def get_conf(indent: bool, verbose: bool, host: str, configpath: Optional[Path]):
    """ Output gRPC services configuration
    """
    conf: Any = load_configuration(configpath, verbose)

    async def _conf(pool):
        await pool.update_backends()
        confdata = await pool.get_config()
        if indent:
            click.echo(json.dumps(json.loads(confdata), indent=4, sort_keys=True))
        else:
            click.echo(confdata)

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_conf(pool))
    else:
        click.echo(f"ERROR: {host} not found", file=sys.stderr)


@conf_commands.command('set')
@click.argument('newconf', nargs=1)
@click.option('--validate', is_flag=True, help="Validate before sending")
@click.option('--diff', is_flag=True, help="Output config diff")
@click.option("--host", help="Watch specific hostname", required=True)
@global_options()
def set_conf(
    newconf: str,
    validate: bool,
    verbose: bool,
    diff: bool,
    host: str,
    configpath: Optional[Path],
):
    """ Change gRPC services configuration

        if NEWCONF starts with a '@' then load the configuration from
        file whose path follow '@'.
    """
    if newconf.startswith('@'):
        newconf = Path(newconf[1:]).open().read()

    if validate:
        # Validate as json
        try:
            json.loads(newconf)
        except json.JSONDecodeError as err:
            click.echo(err, file=sys.stderr)
            sys.exit(1)

    conf: Any = load_configuration(configpath, verbose)

    async def _conf(pool):
        await pool.update_backends()
        jdiff = await pool.set_config(newconf, return_diff=diff)
        if jdiff is not None:
            click.echo(jdiff)
        else:
            click.echo(pool.label)

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_conf(pool))
    else:
        click.echo(f"ERROR: {host} not found", file=sys.stderr)


#
# Catalog
#

@cli_commands.command('catalog')
@click.option("--location", help="Catalog location")
@click.option("--host", help="Watch specific hostname", required=True)
@global_options()
def print_catalog(
    location: Optional[str],
    verbose: bool,
    host: str,
    configpath: Optional[Path],
):
    """ Print catalog for 'host'
    """
    conf: Any = load_configuration(configpath, verbose)

    async def _catalog(pool):
        await pool.update_backends()
        async for item in pool.catalog(location):
            click.echo(json.dumps(item, indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_catalog(pool))
    else:
        click.echo(f"ERROR: {host} not found", file=sys.stderr)

#
# Cache commands
#


@cli_commands.group('cache')
def cache_commands():
    """  Cache management
    """
    pass


#
# Cache list
#

@cache_commands.command('list')
@click.option("--host", help="Watch specific hostname", required=True)
@global_options()
def print_cache_content(verbose: bool, host: str, configpath: Optional[Path]):
    """ Print cache content for 'host'
    """
    conf: Any = load_configuration(configpath, verbose)

    async def _cache_list(pool):
        await pool.update_backends()
        click.echo(json.dumps(await pool.cache_content(), indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_cache_list(pool))
    else:
        click.echo(f"ERROR: {host} not found", file=sys.stderr)


#
# Sync cache
#

@cache_commands.command('sync')
@click.option("--host", help="Watch specific hostname", required=True)
@global_options()
def sync_cache(verbose: bool, host: str, configpath: Optional[Path]):
    """ Synchronize cache content for 'host'
    """
    conf: Any = load_configuration(configpath, verbose)

    async def _sync_cache(pool):
        await pool.update_backends()
        click.echo(json.dumps(await pool.synchronize_cache(), indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_sync_cache(pool))
    else:
        click.echo(f"ERROR: {host} not found", file=sys.stderr)

#
# Cache clear
#


@cache_commands.command('clear')
@click.option("--host", help="Watch specific hostname", required=True)
@global_options()
def clear_cache(verbose: bool, host: str, configpath: Optional[Path]):
    """ Clear cache content for 'host'
    """
    conf: Any = load_configuration(configpath, verbose)

    async def _cache_clear(pool):
        await pool.update_backends()
        await pool.clear_cache()
        click.echo("{}")

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_cache_clear(pool))
    else:
        click.echo(f"ERROR: {host} not found", file=sys.stderr)


#
# Pull projects
#

@cache_commands.command('pull')
@click.argument('projects', nargs=-1)
@click.option("--host", help="Watch specific hostname", required=True)
@global_options()
def pull_projects(
    projects: List[str],
    verbose: bool,
    host: str,
    configpath: Optional[Path],
):
    """ Pull projects in cache for 'host'
    """
    conf: Any = load_configuration(configpath, verbose)

    async def _pull_projects(pool):
        await pool.update_backends()
        click.echo(json.dumps(await pool.pull_projects(*projects), indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_pull_projects(pool))
    else:
        click.echo(f"ERROR: {host} not found", file=sys.stderr)


@cache_commands.command('checkout')
@click.argument('project', nargs=1)
@click.option("--host", help="Checkout project status", required=True)
@global_options()
def checkout_project(
    project: str,
    verbose: bool,
    host: str,
    configpath: Optional[Path],
):
    """ Pull projects in cache for 'host'
    """
    conf: Any = load_configuration(configpath, verbose)

    async def _checkout_project(pool):
        await pool.update_backends()
        click.echo(json.dumps(await pool.checkout_project(project), indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_checkout_project(pool))
    else:
        click.echo(f"ERROR: {host} not found", file=sys.stderr)


@cache_commands.command('drop')
@click.argument('project', nargs=1)
@click.option("--host", help="Drop project from cache", required=True)
@global_options()
def drop_project(
    project: str,
    verbose: bool,
    host: str,
    configpath: Optional[Path],
):
    """ Drop PROJECT from cache for 'host'
    """
    conf: Any = load_configuration(configpath, verbose)

    async def _drop_project(pool):
        await pool.update_backends()
        click.echo(json.dumps(await pool.drop_project(project), indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_drop_project(pool))
    else:
        click.echo(f"ERROR: {host} not found", file=sys.stderr)


@cache_commands.command('info')
@click.argument('project', nargs=1)
@click.option("--host", help="Return project's informations", required=True)
@global_options()
def project_info(
    project: str,
    verbose: bool,
    host: str,
    configpath: Optional[Path],
):
    """ Get project's details
    """
    conf: Any = load_configuration(configpath, verbose)

    async def _project_info(pool):
        await pool.update_backends()
        click.echo(json.dumps(await pool.project_info(project), indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_project_info(pool))
    else:
        click.echo(f"ERROR: {host} not found", file=sys.stderr)

#
# Plugins commands
#


@cli_commands.command('plugins')
@click.option("--host", help="Return project's informations", required=True)
@global_options()
def list_plugins(
    verbose: bool,
    host: str,
    configpath: Optional[Path],
):
    """ List backend's loaded plugins
    """
    conf: Any = load_configuration(configpath, verbose)

    async def _list_plugins(pool):
        await pool.update_backends()
        click.echo(json.dumps(await pool.list_plugins(), indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_list_plugins(pool))
    else:
        click.echo(f"ERROR: {host} not found", file=sys.stderr)


@cli_commands.group('doc')
def doc_commands():
    """ Manage documentation
    """
    pass


@doc_commands.command('openapi')
@click.option("--yaml", "to_yaml", is_flag=True, help="Output as yaml (default: json)")
def dump_swagger_doc(to_yaml: bool):
    """  Output swagger api documentation
    """
    from .server import swagger_model

    doc = swagger_model()
    if to_yaml:
        from ruamel.yaml import YAML
        yaml = YAML()
        yaml.dump(doc.model_dump(), sys.stdout)
    else:
        click.echo(doc.model_dump_json())


@doc_commands.command('config')
@click.option(
    "--format", "out_fmt",
    type=click.Choice(('json', 'yaml', 'toml')),
    default="json",
    help="Select output format",
)
@click.option("--pretty", is_flag=True, help="Pretty format")
def dump_config_schema(out_fmt: str, pretty: bool):
    """  Output configuration schema
    """
    match out_fmt:
        case 'json':
            json_schema = confservice.json_schema()
            indent = 4 if pretty else None
            click.echo(json.dumps(json_schema, indent=indent))
        case 'yaml':
            from ruamel.yaml import YAML
            json_schema = confservice.json_schema()
            yaml = YAML()
            yaml.dump(json_schema, sys.stdout)
        case 'toml':
            confservice.dump_toml_schema(sys.stdout)


@cli_commands.command('serve')
@global_options()
def serve(
    verbose: bool,
    configpath: Optional[Path],
):
    """ Run admin server
    """
    from . import server

    conf: Any = load_configuration(configpath, verbose)
    server.serve(conf)


def main():
    cli_commands()
