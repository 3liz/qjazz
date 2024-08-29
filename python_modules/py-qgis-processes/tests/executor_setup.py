#
# Executor prelude to use with `ipython -i executor_setup.py`
#
import asyncio

from py_qgis_contrib.core import config, logger
from py_qgis_processes.executor import (
    Executor,
    ExecutorConfig,
)

config.confservice.add_section('executor', ExecutorConfig)

logger.setup_log_handler()


def get_executor(update: bool = True) -> Executor:
    ex = Executor(config.confservice.conf.executor)
    services = asyncio.run(ex.update_services())
    print(services)
    return ex
