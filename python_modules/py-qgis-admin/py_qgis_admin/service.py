import asyncio

from typing_extensions import (
    Iterator,
    AsyncIterator,
    Tuple,
    Self,
)

from pydantic import (
    Field,
)

from py_qgis_contrib.core import config, logger  # noqa

from .resolvers import ResolverConfig
from .pools import PoolClient


class ServiceConfig(config.Config):
    resolvers: ResolverConfig = Field(
        default=ResolverConfig(),
    )


class Service:

    def __ini__(self, config: ServiceConfig):
        self._config = config
        self._pools = {}
        self._watchers = {}
        self._watchqueue = asyncio.Queue()
        self._watching = False

    def update_resolvers(self):
        """ Update resolvers
        """
        for resolver in self._config.get_resolvers():
            resolver_id = resolver.name
            if resolver_id not in self._pools:
                # Add new pool from resolver
                self.add_pool(PoolClient(resolver))

    async def _watch(self, pool: PoolClient):
        async for _ in pool.watch():
            if self._watching:
                await self._watchqueue.put(pool)

    def add_pool(self, pool: PoolClient):
        """ Add a pool to monitor
        """
        name = pool.name
        assert name not in self._pools, f"Pool {name} already monitored"
        self._pools[name] = pool
        # Add watcher
        self._watchers[name] = asyncio.create_task(self._watch(pool))

    def pools(self) -> Iterator[PoolClient]:
        """ Return the list of server pools
        """
        return self._pools.values()

    async def watch(self) -> AsyncIterator[Tuple[Self, PoolClient]]:
        """ Wait for state change in one of the worker
        """
        self._watching = True
        try:
            pool = await self._watchqueue.get()
            while pool is not None:
                yield (self, pool)
                pool = await self._watchqueue.get()
        finally:
            self._watching = False
