""" QGIS gRCP CLI administration
"""
import sys
import asyncio
import click
import json

from pathlib import Path
from typing_extensions import (
    Optional,
    List,
)

from py_qgis_contrib.core import config, logger
from .service import (
    Service,
    ResolverConfig,
    PoolClient,
)

RESOLVERS_SECTION = 'resolvers'

# Add the `[resolvers]` configuration section
config.confservice.add_section(RESOLVERS_SECTION, ResolverConfig)


def load_configuration(configpath: Optional[Path]) -> config.Config:
    if configpath:
        cnf = config.read_config_toml(
            configpath,
            location=str(configpath.parent.absolute())
        )
    else:
        cnf = {}
    try:
        config.confservice.validate(cnf)
    except config.ConfigError as err:
        print("Configuration error:", err)
        sys.exit(1)

    logger.setup_log_handler()

    return config.confservice.conf


def get_pool(config, name: str) -> Optional[PoolClient]:
    """ Create a pool client from config
    """
    for resolver in config.get_resolvers():
        if resolver.name == name:
            return PoolClient(resolver)

    # No match in config, try to resolve it
    # directly
    return PoolClient(ResolverConfig.from_string(name))


@click.group()
def cli_commands():
    pass


def print_pool_status(pool, statuses):
    statuses = dict(statuses)
    print(f"{pool.name:<15}", "\tworkers:", len(pool))
    for i, s in enumerate(pool.servers):
        status = "ok" if statuses[s.address] else "unavailable"
        print(f"{i+1:>2}.\t", f"{s.address:<20}", status)

#
# Watch
#


@cli_commands.command('watch')
@click.option("--host", help="Watch specific hostname")
@click.option(
    "--conf", "-C", "configpath",
    envvar="QGIS_GRPC_ADMIN_CONFIGFILE",
    help="configuration file",
    type=click.Path(
        exists=True,
        readable=True,
        dir_okay=False,
        path_type=Path,
    ),
)
def watch(host: Optional[str], configpath: Optional[Path]):
    """ Watch a cluster of qgis gRPC services
    """
    conf = load_configuration(configpath)
    if host:
        async def _watch(pool):
            await pool.update_servers()
            async for statuses in pool.watch():
                print_pool_status(pool, statuses)

        pool = get_pool(conf.resolvers, host)
        if pool is not None:
            asyncio.run(_watch(pool))
        else:
            print("ERROR: ", host, "not found", file=sys.stderr)
    else:
        service = Service(conf.resolvers)
        if not service.num_pools():
            print("No servers", file=sys.stderr)
            return

        async def _watch():
            await service.synchronize()
            async for pool, statuses in service.watch():
                print_pool_status(pool, statuses)

        asyncio.run(_watch())


#
# Stats
#

@cli_commands.command('stats')
@click.option("--host", help="Hostname", required=True)
@click.option("--watch", is_flag=True, help="Check periodically")
@click.option("--interval", help="Check interval (seconds)", default=3)
@click.option(
    "--conf", "-C", "configpath",
    envvar="QGIS_GRPC_ADMIN_CONFIGFILE",
    help="configuration file",
    type=click.Path(
        exists=True,
        readable=True,
        dir_okay=False,
        path_type=Path,
    ),
)
def stats(host: Optional[str], watch: bool, interval: int, configpath: Optional[Path]):
    """ Watch a cluster of qgis gRPC services
    """
    conf = load_configuration(configpath)

    if watch:
        async def _watch(pool):
            await pool.update_servers()
            async for stats in pool.watch_stats(interval):
                print(json.dumps([r for _, r in stats], indent=4, sort_keys=True))

    else:
        async def _watch(pool):
            await pool.update_servers()
            stats = await pool.stats()
            print(json.dumps([r for _, r in stats], indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_watch(pool))
    else:
        print("ERROR: ", host, "not found", file=sys.stderr)

#
# Configuration
#


@cli_commands.command('conf')
@click.option("--host", help="Hostname", required=True)
@click.option(
    "--conf", "-C", "configpath",
    envvar="QGIS_GRPC_ADMIN_CONFIGFILE",
    help="configuration file",
    type=click.Path(
        exists=True,
        readable=True,
        dir_okay=False,
        path_type=Path,
    ),
)
def print_conf(host: Optional[str], configpath: Optional[Path]):
    """ Watch a cluster of qgis gRPC services
    """
    conf = load_configuration(configpath)

    async def _conf(pool):
        await pool.update_servers()
        print(json.dumps(await pool.get_config(), indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_conf(pool))
    else:
        print("ERROR: ", host, "not found", file=sys.stderr)


#
# Catalog
#

@cli_commands.command('catalog')
@click.option("--host", help="Hostname", required=True)
@click.option("--location", help="Catalog location")
@click.option(
    "--conf", "-C", "configpath",
    envvar="QGIS_GRPC_ADMIN_CONFIGFILE",
    help="configuration file",
    type=click.Path(
        exists=True,
        readable=True,
        dir_okay=False,
        path_type=Path,
    ),
)
def print_catalog(host: str, location: Optional[str], configpath: Optional[Path]):
    """ Print catalog for 'host'
    """
    conf = load_configuration(configpath)

    async def _catalog(pool):
        await pool.update_servers()
        async for item in pool.catalog(location):
            print(json.dumps(item, indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_catalog(pool))
    else:
        print("ERROR: ", host, "not found", file=sys.stderr)

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
@click.option("--host", help="Hostname", required=True)
@click.option(
    "--conf", "-C", "configpath",
    envvar="QGIS_GRPC_ADMIN_CONFIGFILE",
    help="configuration file",
    type=click.Path(
        exists=True,
        readable=True,
        dir_okay=False,
        path_type=Path,
    ),
)
def print_cache_content(host: str, configpath: Optional[Path]):
    """ Print cache content for 'host'
    """
    conf = load_configuration(configpath)

    async def _cache_list(pool):
        await pool.update_servers()
        print(json.dumps(await pool.cache_content(), indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_cache_list(pool))
    else:
        print("ERROR: ", host, "not found", file=sys.stderr)


#
# Sync cache
#

@cache_commands.command('sync')
@click.option("--host", help="Hostname", required=True)
@click.option(
    "--conf", "-C", "configpath",
    envvar="QGIS_GRPC_ADMIN_CONFIGFILE",
    help="configuration file",
    type=click.Path(
        exists=True,
        readable=True,
        dir_okay=False,
        path_type=Path,
    ),
)
def sync_cache(host: str, configpath: Optional[Path]):
    """ Synchronize cache content for 'host'
    """
    conf = load_configuration(configpath)

    async def _sync_cache(pool):
        await pool.update_servers()
        print(json.dumps(await pool.synchronize_cache(), indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_sync_cache(pool))
    else:
        print("ERROR: ", host, "not found", file=sys.stderr)


#
# Pull projects
#

@cache_commands.command('pull')
@click.argument('projects', nargs=-1)
@click.option("--host", help="Hostname", required=True)
@click.option(
    "--conf", "-C", "configpath",
    envvar="QGIS_GRPC_ADMIN_CONFIGFILE",
    help="configuration file",
    type=click.Path(
        exists=True,
        readable=True,
        dir_okay=False,
        path_type=Path,
    ),
)
def pull_projects(projects: List[str], host: str, configpath: Optional[Path]):
    """ Pull projects in cache for 'host'
    """
    conf = load_configuration(configpath)

    async def _pull_projects(pool):
        await pool.update_servers()
        print(json.dumps(await pool.pull_projects(*projects), indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_pull_projects(pool))
    else:
        print("ERROR: ", host, "not found", file=sys.stderr)


@cache_commands.command('drop')
@click.argument('project', nargs=1)
@click.option("--host", help="Hostname", required=True)
@click.option(
    "--conf", "-C", "configpath",
    envvar="QGIS_GRPC_ADMIN_CONFIGFILE",
    help="configuration file",
    type=click.Path(
        exists=True,
        readable=True,
        dir_okay=False,
        path_type=Path,
    ),
)
def drop_project(project: str, host: str, configpath: Optional[Path]):
    """ Drop PROJECT from cache for 'host'
    """
    conf = load_configuration(configpath)

    async def _drop_project(pool):
        await pool.update_servers()
        print(json.dumps(await pool.drop_project(project), indent=4, sort_keys=True))

    pool = get_pool(conf.resolvers, host)
    if pool is not None:
        asyncio.run(_drop_project(pool))
    else:
        print("ERROR: ", host, "not found", file=sys.stderr)


def main():
    cli_commands()
