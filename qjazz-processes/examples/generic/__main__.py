import os

from pathlib import Path

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
@click.option(
    "--loglevel",
    "-l",
    type=click.Choice(("error", "warning", "info", "debug")),
    default="info",
    help="Celery log level",
)
@click.option("--dump-config", is_flag=True, help="Dump config and exit")
def run_worker(configpath: Path, loglevel: str, dump_config: bool):
    from qjazz_processes.worker.config import CONFIG_ENV_PATH

    if not configpath:
        configpath = Path(__file__).parent.joinpath("config.toml")

    os.environ[CONFIG_ENV_PATH] = str(configpath)

    if dump_config:
        from qjazz_processes.worker.config import load_configuration
        click.echo(load_configuration().model_dump_json())
    else:
        from .jobs import app
        app.start_worker(loglevel=loglevel)


main()
