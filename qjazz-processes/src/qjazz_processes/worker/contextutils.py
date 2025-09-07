import os

from contextlib import chdir, contextmanager
from pathlib import Path

# from as_core.storage import StorageClient, StorageCreds, storage_client
from qjazz_core import logger


@contextmanager
def execute_context(workdir: Path, task_id: str):
    with chdir(workdir), logger.logfile(workdir, "processing"), memlog(task_id):
        yield


@contextmanager
def memlog(task_id: str):
    import psutil

    process = psutil.Process(os.getpid())
    rss = process.memory_info().rss
    mb = 1024 * 1024.0
    try:
        yield
    finally:
        _leaked = (process.memory_info().rss - rss) / mb
        logger.info("Task %s leaked %.3f Mb", task_id, _leaked)
