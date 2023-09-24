import asyncio
import traceback

from typing_extensions import (
    Iterator,
    AsyncIterator,
    Tuple,
    Sequence,
)

from contextlib import contextmanager

from py_qgis_contrib.core import config, logger  # noqa

from .resolvers import ResolverConfig
from .pool import PoolClient


class Service:

    def __init__(self, resolvers: ResolverConfig):
        self._config = resolvers
        self._pools = {}
        self._watchers = {}
        self._watchqueues = []

    def num_pools(self) -> int:
        return len(self._pools)

    async def synchronize(self):
        """ Update resolvers
        """
        for resolver in self._config.get_resolvers():
            resolver_id = resolver.name
            if resolver_id not in self._pools:
                # Add new pool from resolver
                pool = PoolClient(resolver)
                self._pools[pool.name] = pool
        # Update server and add watcher
        for name, pool in self._pools.items():
            await pool.update_servers()
            if name not in self._watchers:
                self._watchers[name] = asyncio.create_task(self._watch(pool))

    async def _watch(self, pool: PoolClient):
        try:
            async for status in pool.watch():
                for q in self._watchqueues:
                    await q.put((pool, status))
        except Exception:
            logger.error(traceback.format_exc())
            # Remove pool from _watcher list
            self._watchers.pop(pool.name, None)

    @contextmanager
    def _watchqueue(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self._watchqueues.append(queue)
        try:
            yield queue
        finally:
            self._watchqueues.remove(queue)

    def pools(self) -> Iterator[PoolClient]:
        """ Return the list of server pools
        """
        return self._pools.values()

    async def watch(self) -> AsyncIterator[Tuple[PoolClient, Sequence[Tuple[str, bool]]]]:
        """ Wait for state change in one of the worker
        """
        if not self._pools:
            logger.warning("No servers defined")

        with self._watchqueue() as queue:
            pool_status = await queue.get()
            while pool_status is not None:
                yield pool_status
                pool_status = await queue.get()
