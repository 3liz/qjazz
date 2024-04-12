import asyncio
import traceback

from contextlib import asynccontextmanager
from time import time

from pydantic import JsonValue
from typing_extensions import (
    AsyncGenerator,
    Iterable,
    Iterator,
    List,
    Optional,
    Tuple,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import ConfigProxy

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
        self._next_id = config.num_processes
        self._avails: asyncio.Queue = asyncio.Queue()
        self._timeout = config.process_timeout
        self._max_requests = config.max_waiting_requests
        self._count = 0
        self._cached_worker_env = None
        self._cached_worker_plugins: List[_m.PluginInfo] = []
        self._shutdown = False
        self._start_time = time()
        self._update_lock = asyncio.Lock()

    @property
    def workers(self) -> Iterator[Worker]:
        return (w for w in self._workers)

    @property
    def request_pressure(self) -> float:
        return int((self._count / self._max_requests) * 100. + 0.5) / 100.

    @property
    def stopped_workers(self) -> int:
        return sum(1 for w in self._workers if not w.is_alive())

    @property
    def num_workers(self) -> int:
        return len(self._workers)

    @property
    def available_workers(self) -> int:
        return self._avails.qsize()

    @property
    def worker_failure_pressure(self) -> float:
        num = len(self._workers)
        ko = self.stopped_workers
        return int((ko / num) * 100. + 0.5) / 100.

    @property
    def start_time(self) -> int:
        return int(self._start_time)

    @property
    def requests_count(self) -> int:
        return self._count

    def start(self):
        """ Start all worker's processes
        """
        for w in self._workers:
            w.start()

    def terminate_and_join(self, timeout: Optional[int] = 10):
        self._shutdown = True
        for w in self._workers:
            w.terminate()
        for w in self._workers:
            w.join(timeout)

    async def _maintain_pool(self, restore: Optional[Iterable[str]] = None):
        """ Replace dead workers in the worker's list
        """
        replace = []

        def _processes():
            for i, worker in enumerate(self._workers):
                if not worker.is_alive():
                    w = Worker(self._config, name=f"{self._config.name}_{i}")
                    w.start()
                    replace.append((i, w))

        await asyncio.to_thread(_processes)

        if not replace:
            return

        async def _restore(i: int, w: Worker):
            try:
                # Wait for convergence
                await w.ping("")      # Wait for convergence
                self._workers[i] = w  # Replace dead worker

                if restore:
                    for uri in restore:
                        await w.checkout_project(uri, pull=True)

                self._avails.put_nowait(w)
            except Exception:
                logger.error(
                    "Worker initialisation error: %s",
                    traceback.format_exc(),
                )

        await asyncio.gather(*(_restore(i, w) for i, w in replace))

    async def _shrink(self, n: int = 1, restore: Optional[Iterable[str]] = None) -> int:
        """ Decrease the number of processes
        """
        # Pop the next available worker from the queue
        # If one, remove it from the worker list
        # and terminate the process
        #
        # There is no race condition when popping out
        # workers from the available queue
        #
        removed = set()
        for i in range(n):
            try:
                p = self._avails.get_nowait()
                removed.add(self._workers.index(p))
            except asyncio.QueueEmpty:
                break

        if not removed:
            logger.warning("Cannot shrink worker's pool: All workers busy")
            return 0

        size = len(self._workers)
        workers = self._workers

        self._workers = [workers[i] for i in range(size) if i not in removed]
        await self._maintain_pool(restore)

        # Terminate removed workers
        await asyncio.gather(*(workers[i].quit() for i in removed))

        def _join():
            for i in removed:
                w = workers[i]
                w.join(10)

        await asyncio.to_thread(_join)
        return len(removed)

    async def _grow(self, n: int = 1, restore: Optional[Iterable[str]] = None):
        """ Increase the number of processes
        """
        added = []

        def _grow():
            pid = self._next_id
            for i in range(n):
                w = Worker(self._config, name=f"{self._config.name}_{pid}")
                w.start()
                added.append(w)
                pid += 1

        self._next_id += n

        await asyncio.to_thread(_grow)

        async def _restore(w: Worker):
            try:
                # Wait for convergence
                await w.ping("")      # Wait for convergence
                if restore:
                    for uri in restore:
                        await w.checkout_project(uri, pull=True)

                self._workers.append(w)
                self._avails.put_nowait(w)
            except Exception:
                logger.error(
                    "Worker initialisation error: %s",
                    traceback.format_exc(),
                )

        await asyncio.gather(*(_restore(w) for w in added))
        await self._maintain_pool(restore)

    async def maintain_pool(self, restore: Optional[Iterable[str]] = None):
        """ Maintain the number of processes
        """
        async with self._update_lock:
            procs = len(self._workers)
            cur = self._config.num_processes
            if cur > procs:
                logger.info("Scaling up workers to % s", cur)
                await self._grow(cur - procs, restore)
            elif cur < procs:
                logger.info("Scaling down workers to %s", cur)
                await self._shrink(procs - cur, restore)
            else:
                logger.info(
                    "Restoring workers (%s dead workers on %s)",
                    self.stopped_workers,
                    self.num_workers,
                )
                await self._maintain_pool(restore)

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
        if self._shutdown:
            raise WorkerError(503, "Server shutdown")
        if self._count >= self._max_requests:
            raise WorkerError(503, "Maximum number of waiting requests reached")

        try:
            self._count += 1
            # Wait for available worker
            if logger.isEnabledFor(logger.LogLevel.TRACE):
                logger.trace(
                    "POOL: get_worker: Available workers=%s, waiting requests=%s",
                    self._avails.qsize(),
                    self._count,
                )
            try:
                worker = await asyncio.wait_for(self._avails.get(), self._timeout)
            except asyncio.TimeoutError:
                # No worker's available
                worker = None
                raise WorkerError(503, "Server busy")
            yield worker
        except asyncio.TimeoutError:
            logger.critical("Worker stalled, terminating...")
            worker.terminate()  # This will trigger a SIGCHLD signal
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
                    worker.terminate()  # This will trigger a SIGCHLD signal
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
            by drying out the queue.
            Yield an iterator for all workers and restore
            them on the queue when the manager exit

            Used for batch processing the pool
        """
        # Dry out the queue
        if self._count >= self._max_requests:
            raise WorkerError(503, "Maximum number of waiting requests reached")
        if self._shutdown:
            raise WorkerError(503, "Server shutdown")

        async with self._update_lock:
            try:
                count = self.num_workers - self.stopped_workers
                workers = [
                    await asyncio.wait_for(self._avails.get(), self._timeout)
                    for _ in range(count)
                ]
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

    async def update_config(
        self,
        worker_conf: WorkerConfig,
        restore: Optional[Iterable[str]] = None,
    ):
        """ Update config for all workers
        """
        self._config = worker_conf
        self._timeout = self._config.process_timeout
        self._max_requests = self._config.max_waiting_requests
        # Update log level
        level = logger.set_log_level()
        logger.info("Log level set to %s", level.name)

        # Update configs for live workers
        await asyncio.gather(
           *(w.update_config(self._config) for w in self._workers if w.is_alive()),
        )

        # Restore pool
        await self.maintain_pool(restore)

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
