
import asyncio
import pickle
import tempfile
import traceback

from pathlib import Path

from py_qgis_contrib.core import logger

from .messages import CacheInfo
from .messages import CheckoutStatus as Co
from .pool import WorkerConfig, WorkerPool


class Restore:

    def __init__(self):
        self._last = set()
        self._curr = set()
        self._path = Path(tempfile.gettempdir(), 'qgis-server.cached')
        self._save_task = None

    async def restore(self, pool: WorkerPool):
        """ Load restore list and pull projects into
            workers
        """
        if not self._path.exists():
            # Nothing to do
            return

        try:
            logger.info("Restoring cache list")
            with self._path.open('rb') as io:
                self._last = pickle.load(io)
                self._curr = self._last.copy()

            logger.trace("Cache list:  %s", self._curr)

            async def _pull(w):
                for uri in self._curr:
                    resp = await w.checkout_project(uri, pull=True)
                    logger.trace(
                        "RESTORE: Loaded %s in worker %s (status %s)",
                        uri, w.name, resp.status.name
                    )

            # Pull projects into workers
            asyncio.gather(*(_pull(w) for w in pool.workers), return_exceptions=True)

        except Exception:
            logger.error(
                "Failed to load restore list %s",
                traceback.format_exc()
            )
            raise

    def _commit(self):
        if self._last != self._curr and not self._save_task:
            async def _save():
                await asyncio.sleep(10)
                logger.debug("Updating restore cache list")
                try:
                    with self._path.open('wb') as io:
                        pickle.dump(self._curr, io)
                    self._last = self._curr.copy()
                except Exception:
                    logger.error(
                        "Failed to save restore list %s",
                        traceback.format_exc()
                    )
                finally:
                    self._save_task = None
            self._save_task = asyncio.create_task(_save())

    def clear(self):
        self._curr.clear()
        self._commit()

    def update(self, resp: CacheInfo):
        match resp.status:
            case Co.NEW | Co.UPDATED | Co.UNCHANGED:
                self._curr.add(resp.uri)
            case Co.REMOVED | Co.NOTFOUND:
                self._curr.discard(resp.uri)
        self._commit()


#
# Dummy restore if restore cache is disabled
#
class RestoreNoop:

    async def restore(self, pool: WorkerPool):
        pass

    def clear(self):
        pass

    def update(self, uri: str):
        pass


def create_restore_object(config: WorkerConfig):
    if config.restore_cache:
        return Restore()
    else:
        return RestoreNoop()
