import asyncio
import traceback

from contextlib import asynccontextmanager

from typing_extensions import (
    Iterator,
    Dict,
    Tuple,
    Optional,
)

from .worker import Worker, WorkerError
from .config import WorkerConfig

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import ConfigProxy

from . import messages as _m


class WorkerPool:
    """ A pool of worker using fair balancing
        for executing tasks

        Management tasks are broadcasted to all workers
    """

    def __init__(self, config: WorkerConfig, num_workers: int = 1):
        self._config = config
        self._workers = [Worker(config, name=f"{config.name}_{n}") for n in range(num_workers)]
        self._avails = asyncio.Queue()
        self._timeout = config.worker_timeout
        self._max_requests = config.max_waiting_requests
        self._count = 0
        self._cached_worker_env = None
        self._cached_worker_plugins = None
        self._shutdown = False

    def start(self):
        """ Start all worker's processes
        """
        for w in self._workers:
            w.start()

    def terminate_and_join(self):
        self._shutdown = True
        for w in self._workers:
            w.terminate()
        for w in self._workers:
            w.join()

    async def initialize(self):
        """ Test that workers are alive
            and populate the queue
        """
        for w in self._workers:
            w.ping("")
            self._avails.put_nowait(w)
        # Cache immutable status
        await self._cache_worker_status()

    async def _cache_worker_status(self):
        worker = self._workers[0]
        # Cache environment since it is immutable
        logger.debug("Caching workers status")
        self._cached_worker_env = await worker.env()
        _, items = await worker.list_plugins()
        if items:
            self._cached_worker_plugins = [item async for item in items]
        else:
            self._cached_worker_plugins = []
        #
        # Update status metadata
        #
        self._cached_worker_env.update(
            name=self._config.name,
            num_workers=len(self._workers),
            description=self._config.description,
        )

    @asynccontextmanager
    async def get_worker(self) -> Worker:
        """ Lock context

            - Prevent race condition on worker
            - Prevent request piling
            - Handle client disconnection
            - Handle execution errors
            - Handle stalled/long running job
        """
        if self._count >= self._max_requests:
            raise WorkerError(503, "Maximum number of waiting requests reached")
        if self._shutdown:
            raise WorkerError(503, "Server shutdown")
        try:
            self._count += 1
            # Wait for available worker
            worker = None
            if logger.isEnabledFor(logger.LogLevel.TRACE):
                logger.trace(
                    "POOL: get_worker: Available workers=%s, waiting requests=%s",
                    self._avails.qsize(),
                    self._count,
                )
            worker = await asyncio.wait_for(self._avails.get(), self._timeout)
            yield worker
        except asyncio.TimeoutError:
            logger.critical("Worker stalled, terminating...")
            self._shutdown = True
            worker.terminate()  # This well trigger a SIGCHLD signal
            worker = None       # Do not put back worker on queue
            raise WorkerError(503, "Server stalled")
        except asyncio.CancelledError:
            logger.error("Connection cancelled by client")
            if worker:
                # Flush stream from current task
                await self._worker.consume_until_task_done()
        except Exception as err:
            logger.critical(traceback.format_exc())
            raise WorkerError(500, str(err))
        finally:
            self._count -= 1
            if worker:
                self._avails.put_nowait(worker)

    @asynccontextmanager
    async def wait_for_all_workers(self) -> Iterator[Worker]:
        """ Wait for all workers to be available
            by drying ou the queue.
            Yield an iterator for all workers and restore
            them on the queue when the manager exit

            Used for batch processing the pool
        """
        # Dry out the queue
        if self._count >= self._max_requests:
            raise WorkerError(503, "Maximum number of waiting requests reached")
        if self._shutdown:
            raise WorkerError(503, "Server shutdown")

        try:
            count = len(self._workers)
            workers = [await asyncio.wait_for(self._avails.get(), self._timeout) for _ in range(count)]
        except asyncio.TimeoutError:
            raise WorkerError(503, "Server stalled")

        self._count += 1
        try:
            yield (w for w in workers)
        except asyncio.CancelledError:
            logger.error("Connection cancelled by client")
            # Flush stream from current task
            for w in workers:
                await w.consume_until_task_done()
        except Exception as err:
            logger.critical(traceback.format_exc())
            raise WorkerError(500, str(err))
        finally:
            self._count -= 1
            # Restore workers
            for w in workers:
                self._avails.put_nowait(w)

    #
    # Config
    #

    @property
    def config(self) -> WorkerConfig:
        return self._config

    def dump_config(self) -> Dict:
        if isinstance(self._config, ConfigProxy):
            return self._config.service.conf.model_dump()
        else:
            return self._config.model_dump()

    async def update_config(self, obj: Dict):
        """ Update config for all workers
        """
        if isinstance(self._config, ConfigProxy):
            async with self.wait_for_all_workers() as workers:
                self._config.service.update_config(obj)
                # Update timeout config
                self._timeout = self._config.worker_timeout
                self._max_requests = self._config.max_waiting_requests
                # Update log level
                level = logger.set_log_level()
                logger.info("Log level set to %s", level.name)
                for w in workers:
                    await w.update_config(obj)
                logger.trace("Updated workers with configuration\n %s", obj)
        else:
            raise WorkerError(403, "Cannot update local configuration")

    #
    # Env
    #

    @property
    def env(self) -> Dict:
        return self._cached_worker_env

    #
    # Plugins
    #

    def list_plugins(self) -> Tuple[int, Optional[Iterator[_m.PluginInfo]]]:
        count = len(self._cached_worker_plugins)
        if count == 0:
            return (count, None)
        else:
            return (count, (item for item in self._cached_worker_plugins))
