#
# Executor prelude to use with `ipython -i executor_setup.py`
#
import os

from pathlib import Path

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


# Set config path for worker
os.environ['PY_QGIS_PROCESSES_WORKER_CONFIG'] = str(Path(__file__).parent / "worker-config.toml")
