#
# Executor prelude to use with `ipython -i executor_setup.py`
#
import os

from pathlib import Path

from qjazz_core import config, logger

from qjazz_processes.executor.blocking import (
    BlockingExecutor,
    ExecutorConfig,
)

confservice = config.ConfBuilder()
confservice.add_section("logging", logger.LoggingConfig)
confservice.add_section("executor", ExecutorConfig)

logger.setup_log_handler(confservice.conf.logging.level) # type: ignore [attr-defined]


def Executor() -> BlockingExecutor:
    return BlockingExecutor(confservice.conf.executor) # type: ignore [attr-defined]


# Set config path for worker
os.environ["PY_QGIS_PROCESSES_WORKER_CONFIG"] = str(Path(__file__).parent / "worker-config.toml")
