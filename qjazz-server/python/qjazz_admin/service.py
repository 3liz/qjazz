import asyncio
import traceback

from contextlib import contextmanager
from typing import (
    AsyncIterator,
    Dict,
    Generator,
    Iterable,
    Iterator,
    Sequence,
    Tuple,
)

from qjazz_contrib.core import config, logger  # noqa

from .backend import RECONNECT_DELAY
from .pool import PoolClient
from .resolvers import ResolverConfig


class Service:
    """ Handle all pools (clusters) of gRPC servers
    """

    def __init__(self, resolvers: ResolverConfig):
        self._config = resolvers
        self._pools: Dict[str, PoolClient] = {}
        self._sync_events: Tuple[asyncio.Event, ...] = ()
        self._shutdown = False
        self.update_pools()

    def __getitem__(self, label: str) -> PoolClient:
        return self._pools[label]

    def __contains__(self, label: str) -> bool:
        return label in self._pools

    def num_pools(self) -> int:
        return len(self._pools)

    def update_pools(self) -> Iterable[str]:
        """ Update resolvers

            Returns removed pools label
        """
        def _resolve():
            for resolver in self._config.get_resolvers():
                resolver_id = resolver.label
                if resolver_id not in self._pools:
                    # Add new pool from resolver
                    pool = PoolClient(resolver)
                    self._pools[pool.label] = pool
                yield resolver_id

        removed = set(self._pools.keys())
        removed.difference_update(_resolve())
        return removed

    async def shutdown(self):
        self._shutdown = True
        self._sync()
        for pool in self._pools.values:
            await pool.shutdown()

    async def synchronize(self):
        removed = self.update_pools()
        # Clean dead pools
        for label in removed:
            logger.debug("Removing pool %s", label)
            pool = self._pools.pop(label)
            await pool.shutdown()

        # Resync pools
        for name, pool in self._pools.items():
            await pool.update_backends()
        self._sync()

    @contextmanager
    def sync_event(self) -> Generator[asyncio.Event, None, None]:
        """ Return a new event for synchronization
        """
        event = asyncio.Event()
        self._sync_events += (event,)
        try:
            yield event
        finally:
            evts = self._sync_events
            self._sync_events = tuple(e for e in evts if e is not event)

    def _sync(self):
        """ Set all synchronization events
        """
        for evt in self._sync_events:
            evt.set()

    @property
    def pools(self) -> Iterator[PoolClient]:
        """ Return the list of server pools
        """
        return iter(self._pools.values())

    async def watch(self) -> AsyncIterator[Tuple[PoolClient, Sequence[Tuple[str, bool]]]]:
        """ Wait for state change in one of the worker
        """
        # See https://github.com/python/mypy/issues/4052
        queue: asyncio.Queue = asyncio.Queue()
        exception = None

        async def _watch(pool):
            nonlocal exception
            try:
                async for result in pool.watch():
                    await queue.put((pool, result))
            except Exception as err:
                logger.error(traceback.format_exc())
                exception = err

        with self.sync_event() as sync:  # type: ignore

            async def _sentinel():
                await sync.wait()
                queue.put_nowait(None)

            while not self._shutdown:
                try:
                    watchers = tuple(asyncio.create_task(_watch(p)) for p in self._pools.values())
                    sentinel = asyncio.create_task(_sentinel())
                    while True:
                        result = await queue.get()
                        if result is None:
                            break
                        if exception:
                            sentinel.cancel()
                            raise exception
                        yield result
                finally:
                    # Cancel watchers
                    for w in watchers:
                        w.cancel()
                sync.clear()
                if not self._shutdown:
                    await asyncio.sleep(RECONNECT_DELAY)
