#
# Executor prelude to use with `ipython -i executor_setup.py`
#
import click

from py_qgis_contrib.core import config, logger
from py_qgis_processes.executor import (
    Executor,
    ExecutorConfig,
)


def read_configuration():
    config.confservice.add_section('executor', ExecutorConfig)

    logger.setup_log_handler()


def init() -> Executor:
    conf = read_configuration()
    executor = Executor(conf.executor)
    executor.update_services()
    return executor


@click.group()
def main():
    pass


@main.command('services')
def list_services():
    pass


@main.command('restart')
def restart_pool():
    pass


@main.command('shutdown')
def shutdown_worker():
    pass
