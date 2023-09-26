import asyncio
import traceback
import grpc
from py_qgis_worker._grpc import api_pb2

from google.protobuf import json_format
from contextlib import contextmanager
from typing_extensions import (
    Optional,
    Dict,
    List,
    Tuple,
    Sequence,
    AsyncIterator,
    Iterator,
)

from py_qgis_contrib.core import logger

from .client import (
    PoolItemClient,
    RECONNECT_DELAY,
)

from .resolvers import Resolver
from .errors import (
    ServiceNotAvailable,
)


def MessageToDict(message) -> Dict:
    return json_format.MessageToDict(
        message,
        including_default_value_fields=True,
        preserving_proto_field_name=False,
    )


def reduce_cache(acc: Dict, item: api_pb2.CacheInfo) -> Dict:
    """ Reduce cache info and check for consistency

        If status are not the same (cache not sync'ed) then
        set the status to 'None'
    """
    status = acc.status
    if status and status != item.status:
        acc.update(status=None)
    try:
        assert acc['name'] == item.name
        assert acc['lastModified'] == item.last_modified
        assert acc['savedVersion'] == item.saved_version
    except AssertionError:
        logger.error("Mismatched cache info for %s", item.uri)
    return acc


class PoolClient:
    """ Admin tool for cluster of gRCP servers

        All clients sharing a cluster must share the exact same
        configuration.

        Usually these are set of single servers were ips are
        resolved from single host (scaled docker containers
        from docker-compose or swarm services).
    """

    def __init__(self, resolver: Resolver):
        self._resolver = resolver
        self._servers = []
        self._tasks = []
        self._shutdown = False
        self._sync_events = ()

    def __len__(self):
        return len(self._servers)

    @property
    def name(self) -> str:
        return self._resolver.name

    def shutdown(self):
        self._shutdown = True
        self._sync()
        for s in self._servers:
            s.shutdown()

    @contextmanager
    def sync_event(self) -> asyncio.Event:
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
    def servers(self) -> Sequence[PoolItemClient]:
        for server in self._servers:
            yield server

    @property
    async def check_servers(self) -> Tuple[int, int]:
        """ Return a tuple of (reachables, unreachables)
            server count
        """
        reachables = 0
        unreachables = 0
        for s in self._servers:
            if await s.check():
                reachables += 1
            else:
                unreachables + 1
        return (reachables, unreachables)

    async def enable_servers(self, enable: bool):
        for s in self._servers:
            s.enable_servers(enable)

    async def update_servers(self):
        """ Set up all clients from resolver
            The network configuration may have changed,
            in particular when containers ared added/removed
            from docker services.

            We ask for a new updated list of servers from
            the resolver.
        """
        configs = {conf.address_to_string(): conf for conf in await self._resolver.configs}
        addresses = set(configs)

        current_addr = set(s.address for s in self._servers)

        new_addr = addresses.difference(current_addr)
        removed_addr = current_addr.difference(addresses)

        if not new_addr and not removed_addr:
            return

        def _update():
            for server in self._servers:
                if server.address in removed_addr:
                    logger.warning(
                        "Removing server at '%s' (%s)",
                        server.address,
                        self.name,
                    )
                    server.shutdown()
                else:
                    # Keep current servers
                    yield server
            for address in new_addr:
                # Add new server
                logger.debug("Adding server [%s] for pool %s", address, self.name)
                yield PoolItemClient(configs[address])

        # Update server list
        self._servers = list(_update())
        # Sync watchers
        self._sync()

    async def watch(self) -> AsyncIterator[Tuple[Tuple[str, bool], ...]]:
        """ Wait for state change in one of the worker
        """
        queue = asyncio.Queue()
        exception = None

        async def _watch(server):
            nonlocal exception
            try:
                async for result in server.watch():
                    await queue.put(result)
            except Exception as err:
                logger.error(traceback.format_exc())
                exception = err

        with self.sync_event() as sync:
            while not self._shutdown:
                exception = None
                try:
                    # Reconnect
                    statuses = {s.address: await s.check() for s in self._servers}
                    yield tuple(statuses.items())

                    watchers = tuple(asyncio.create_task(_watch(s)) for s in self._servers)
                    while watchers:
                        done, pending = await asyncio.wait(
                            (sync.wait(), queue.get()),
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        # Cancel pendings futures
                        for t in pending:
                            t.cancel()
                        if exception:
                            raise exception
                        # Asked for resync
                        if sync.is_set():
                            break
                        server, status = done.pop().result()
                        # Yield on change
                        if status != statuses[server.address]:
                            statuses[server.address] = status
                            yield tuple(statuses.items())
                except StopAsyncIteration:
                    # Client was shutdown
                    logger.trace("%s: client shutdown (StopAsyncIteration)")
                    pass
                finally:
                    # Cancel watchers
                    for w in watchers:
                        w.cancel()
                sync.clear()
                if not self._shutdown:
                    await asyncio.sleep(RECONNECT_DELAY)

    async def stats(self) -> Sequence[Tuple[PoolItemClient, Optional[Dict]]]:
        """  Return stats for all servers
        """
        async def _stats(server):
            try:
                msg = MessageToDict(await server.stats())
                msg.update(address=server.address, status="ok")
                return server, msg
            except grpc.RpcError as err:
                if err.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.error("Server '{server.name}' is unreachable")
                    return (server, dict(address=server.address, status="unavailable"))
                else:
                    raise

        return await asyncio.gather(*(_stats(s) for s in self._servers))

    async def watch_stats(
        self,
        interval: int = 3,
    ) -> AsyncIterator[Sequence[Tuple[PoolItemClient, Optional[Dict]]]]:
        """ Watch service stats
        """
        def _to_dict(item, stats):
            if stats:
                resp = MessageToDict(stats)
                resp.update(address=item.address, status="ok")
            else:
                resp = dict(address=item.address, status="unreachable")
            return item, resp

        with self.sync_event() as sync:
            while not self._shutdown:
                try:
                    # Reconnect
                    _watchers = tuple(s.watch_stats(interval) for s in self._servers)
                    while _watchers:
                        results = await asyncio.gather(*(anext(w) for w in _watchers))
                        yield tuple(_to_dict(item, stats) for item, stats in results)
                        if sync.is_set():
                            break
                except StopAsyncIteration:
                    # Client was shutdown
                    logger.trace("%s: client shutdown (StopAsyncIteration)", self.name)
                    pass
                sync.clear()
                if not self.shutdown:
                    await asyncio.sleep(RECONNECT_DELAY)

    #
    # Cache
    #

    async def reduce_server_cache(self, server) -> Iterator[Dict]:
        """ Consolidate cache for client
        """
        cached_status = {}
        try:
            async for item in server.list_cache():
                status = cached_status.get(item.uri)
                if not status:
                    status = MessageToDict(item)
                    status.update(serverAddress=server.address)
                    del status['cacheId']
                    cached_status[status['uri']] = status
                else:
                    reduce_cache(status, item)
        except grpc.RpcError as rpcerr:
            logger.error(
                "Failed to retrieve cache for %s: %s\t%s",
                server.address,
                rpcerr.code(),
                rpcerr.details()
            )
            cached_status.clear()
        return cached_status.values()

    async def cache_content(self) -> Dict[str, List[Dict]]:
        """ Build a synthetic/consolidated view
            of the cache contents from all
            servers in the cluster.

            Return a dict of cached status list grouped
            by server instance.
        """
        all_status = await asyncio.gather(
            *(self.reduce_server_cache(s) for s in self._servers)
        )

        result = {}
        # Organize by cache uri
        for status_list in all_status:
            for item in status_list:
                bucket = result.setdefault(item['uri'], [])
                bucket.append(item)

        return result

    async def synchronize_cache(self) -> Dict[str, List[Dict]]:
        """ Synchronize all caches
            for all instances
        """
        uris = set()

        async def _collect(server):
            try:
                async for item in server.list_cache():
                    uris.add(item.uri)
            except grpc.RpcError as rpcerr:
                logger.error(
                    "Failed to retrieve cache for %s: %s\t%s",
                    server.address,
                    rpcerr.code(),
                    rpcerr.details()
                )

        await asyncio.gather(*(_collect(s) for s in self._servers))

        result = {uri: [] for uri in uris}

        async def _reduce(server):
            async for item in server.pull_projects(*uris):
                rv = MessageToDict(item)
                rv.update(serverAddress=server.address)
                del rv['cacheId']
                result[item.uri].append(rv)

        await asyncio.gather(*(_reduce(s) for s in self._servers))
        return result

    async def clear_cache(self) -> None:
        """ Clear cache for all servers
        """
        serving = False
        for server in self._servers:
            try:
                await server.clear_cache()
                serving = True
            except grpc.RpcError as err:
                if err.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.error("Server '{server.name}' is unreachable")
                else:
                    raise
        if not serving:
            raise ServiceNotAvailable(self.name)

    async def pull_projects(self, *uris) -> Dict[str, List[Dict]]:
        """ Pull/Update projects in all cache
        """
        rv = {}
        serving = False
        for server in self._servers:
            try:
                cached = {}
                async for item in server.pull_projects(*uris):
                    _item = cached.get(item.uri)
                    if not _item:
                        _item = MessageToDict(item)
                        _item.update(serverAddress=server.address)
                        cached[item.uri] = _item
                    else:
                        reduce_cache(_item, item)
                for uri, _item in cached.items():
                    rv.setdefault(uri, []).append(_item)
                serving = True
            except grpc.RpcError as err:
                if err.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.error("Server '{server.name}' is unreachable")
                else:
                    raise

        if not serving:
            raise ServiceNotAvailable(self.name)
        return rv

    #
    # Catalog
    #

    async def catalog(self, location: Optional[str] = None) -> AsyncIterator[Dict]:
        """ Return the catalog
        """
        # Find a serving server
        # All servers share the same config so
        # find a serving to get the catalog
        serving = False
        for s in self._servers:
            try:
                async for item in s.catalog(location):
                    yield MessageToDict(item)
                serving = True
            except grpc.RpcError as rpcerr:
                logger.trace("%s\t%s\t%s", self._server_address, rpcerr.code(), rpcerr.details())
                if rpcerr.code() == grpc.StatusCode.UNAVAILABLE:
                    continue
                else:
                    raise
        if not serving:
            raise ServiceNotAvailable(self.name)

    #
    # Conf
    #

    async def get_config(self) -> Dict:
        """ Return the configuration
        """
        # Find a serving server
        # All servers share the same config
        serving = False
        for s in self._servers:
            try:
                return await s.get_config()
                serving = True
            except grpc.RpcError as rpcerr:
                logger.trace("%s\t%s\t%s", self._server_address, rpcerr.code(), rpcerr.details())
                if rpcerr.code() == grpc.StatusCode.UNAVAILABLE:
                    continue
                else:
                    raise
        if not serving:
            raise ServiceNotAvailable(self.name)
