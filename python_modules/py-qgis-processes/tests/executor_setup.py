#
# Executor prelude to use with `ipython -i executor_setup.py`
#

from py_qgis_contrib.core import config, logger
from py_qgis_processes.executor import (
    Executor as _Executor,
)
from py_qgis_processes.executor import (
    ExecutorConfig,
)

config.confservice.add_section('executor', ExecutorConfig)

logger.setup_log_handler()


def Executor() -> _Executor:
    return _Executor(config.confservice.conf.executor)
