""" QGIS gRCP CLI administration
"""

import sys
import asyncio  # noqa
import click

from pathlib import Path
from typing_extensions import (
    Optional,
)

from py_qgis_contrib.core import config

from .service import (  # noqa
    ServiceConfig,
    Service,
)

RESOLVERS_SECTION = 'resolvers'

# Add the `[resolvers]` configuration section
config.confservice.add_section(RESOLVERS_SECTION, ServiceConfig)


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
    return config.confservice.conf


@click.group()
def cli_commands():
    pass


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
def watch(host: Optional[str], conf: Optional[Path]):
    """ Watch a cluster of qgis gRPC services
    """
    ...
