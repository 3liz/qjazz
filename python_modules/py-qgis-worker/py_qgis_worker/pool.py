import asyncio
import traceback

from contextlib import asynccontextmanager
from time import time

from pydantic import JsonValue
from typing_extensions import AsyncGenerator, Dict, Iterator, List, Optional, Tuple

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import ConfigError, ConfigProxy

from . import messages as _m
from .config import WorkerConfig
from .worker import Worker, WorkerError


class WorkerPool:
    """ A pool of worker using fair balancing
        for executing tasks

        Management tasks are broadcasted to all workers
    """

    def __init__(self, config: WorkerConfig):
        self._config = config
        self._workers = [Worker(
            config,
            name=f"{config.name}_{n}",
        ) for n in range(config.num_processes)]
        self._avails: asyncio.Queue = asyncio.Queue()
        self._timeout = config.process_timeout
        self._max_requests = config.max_waiting_requests
        self._count = 0
        self._cached_worker_env = None
        self._cached_worker_plugins: List[_m.PluginInfo] = []
        self._shutdown = False
        self._start_time = time()

    @property
    def workers(self) -> Iterator[Worker]:
        return (w for w in self._workers)

    @property
    def request_pressure(self) -> float:
        return (int((self._count / self._max_requests) + 0.5) * 100.) / 100.

    @property
    def stopped_workers(self) -> int:
        return sum(1 for w in self._workers if not w.is_alive())

    @property
    def num_workers(self) -> int:
        return len(self._workers)

    @property
    def worker_failure_pressure(self) -> float:
        num = len(self._workers)
        ko = self.stopped_workers
        return (int((ko / num) + 0.5) * 100.) / 100.

    @property
    def start_time(self) -> int:
        return int(self._start_time)

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
            await w.ping("")
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
            num_processes=len(self._workers),
            description=self._config.description,
        )

    @asynccontextmanager
    async def get_worker(self) -> AsyncGenerator[Worker, None]:
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
                # Handle timeout, since the main reason
                # for cancelling may be a stucked or
                # long polling response.
                try:
                    await asyncio.wait_for(
                        worker.consume_until_task_done(),
                        self._timeout,
                    )
                except asyncio.TimeoutError:
                    logger.critical("Worker stalled, terminating...")
                    self._shutdown = True
                    worker.terminate()  # This well trigger a SIGCHLD signal
                    worker = None       # Do not put back worker on queue
        except WorkerError:
            raise
        except Exception as err:
            logger.critical(traceback.format_exc())
            raise WorkerError(500, str(err))
        finally:
            self._count -= 1
            if worker:
                self._avails.put_nowait(worker)

    @asynccontextmanager
    async def wait_for_all_workers(self) -> AsyncGenerator[Iterator[Worker], None]:
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
        except WorkerError:
            raise
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

    def config_dump_json(self) -> str:
        if isinstance(self._config, ConfigProxy):
            return self._config.service.conf.model_dump_json()
        else:
            return self._config.model_dump_json()

    async def update_config(self, obj: Dict):
        """ Update config for all workers
        """
        if isinstance(self._config, ConfigProxy):
            async with self.wait_for_all_workers() as workers:
                try:
                    self._config.service.update_config(obj)
                except ConfigError as err:
                    raise WorkerError(400, err.json(include_url=False)) from None
                # Update timeout config
                self._timeout = self._config.process_timeout
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
    def env(self) -> JsonValue:
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
