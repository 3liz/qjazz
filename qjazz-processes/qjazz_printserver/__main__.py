import os

from pathlib import Path

import click

PathType = click.Path(
    exists=True,
    readable=True,
    dir_okay=False,
    path_type=Path,
)


@click.command()
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
    help="Log level",
)
@click.option("--dump", is_flag=True, help="Dump config and exit")
def run_worker(
    configpath: Path,
    loglevel: str,
    dump: bool,
):
    """Run printserver processes worker"""
    from qjazz_processes.worker.config import CONFIG_ENV_PATH

    if configpath:
        os.environ[CONFIG_ENV_PATH] = str(configpath)

    if dump:
        from pydantic import BaseModel
        from typing_extensions import cast

        from qjazz_processes.worker.config import load_configuration

        conf = cast(BaseModel, load_configuration())
        click.echo(conf.model_dump_json(indent=4))
    else:
        from .jobs import app

        app.start_worker(loglevel=loglevel)


def main():
    run_worker()


main()
