# Posix semaphore
# see https://github.com/osvenskan/posix_ipc/blob/develop/USAGE.md
#
from contextlib import contextmanager
from typing import Generator, Optional

from posix_ipc import O_CREAT, Semaphore

from qjazz_contrib.core import logger


@contextmanager
def semaphore(name: str, *, timeout: Optional[int] = None) -> Generator:
    """Create a posix kernel semaphore"""

    name = name.removeprefix("/").translate(
        # Dunno why Mypy choke on this
        str.maketrans({'/': '_', '.': '_'})  # type: ignore [arg-type]
    )
    logger.debug("Getting semaphore %s", name)
    sem = Semaphore(name, O_CREAT, initial_value=1)
    sem.acquire()
    try:
        yield sem
    finally:
        sem.release()
        sem.close()
