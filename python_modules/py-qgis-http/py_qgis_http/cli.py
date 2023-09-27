import sys
import asyncio
import click

from py_qgis_contrib.core import config;

from .config import (
    HttpConfig,
    ServicesConfig,
)

HTTP_SECTION = 'http'
SERVICES_SECTION = 'services'

# Add the `[http]` configuration section
config.confservice.add_section(HTTP_SECTION, HttpConfig)

# Add the `[services]` configuration section
config.confservice.add_section(SERVICES_SECTION, ServicesConfig)

#
# Load configuration file
#

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


@cli_commands.command('serve')
@click.option(
    "--conf", "-C", "configpath",
    envvar="QGIS_HTTP_CONFIGFILE",
    help="configuration file",
    type=click.Path(
        exists=True,
        readable=True,
        dir_okay=False,
        path_type=Path
    ),
)
def serve_http(configpath: ServerConfig):
    
    conf = load_configuration(configpath)
    logger.setup_log_handler(conf.logging.level)

    pool = WorkerPool(config.ConfigProxy(WORKER_SECTION), num_processes)
    pool.start()
    try:
        asyncio.run(serve(pool))
    finally:
        pool.terminate_and_join()
        logger.info("Server shutdown")


