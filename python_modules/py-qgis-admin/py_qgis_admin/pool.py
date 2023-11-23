import asyncio
import json
import traceback

from contextlib import contextmanager

import grpc
import jsondiff

from google.protobuf import json_format
from pydantic import Json
from typing_extensions import (
    AsyncIterator,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
)

from py_qgis_contrib.core import logger
from py_qgis_worker._grpc import api_pb2

from .backend import RECONNECT_DELAY, Backend
from .errors import RequestArgumentError, ServiceNotAvailable
from .resolvers import Resolver


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
        self._backends = []
        self._tasks = []
        self._shutdown = False
        self._sync_events = ()

    def __len__(self):
        return len(self._backends)

    @property
    def label(self) -> str:
        return self._resolver.label

    @property
    def address(self) -> str:
        return self._resolver.address

    async def shutdown(self):
        self._shutdown = True
        self._sync()
        for s in self._backends:
            await s.shutdown()

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
    def backends(self) -> Sequence[Backend]:
        for server in self._backends:
            yield server

    async def enable_backends(self, enable: bool):
        for s in self._backends:
            s.enable_server(enable)

    async def update_backends(self):
        """ Set up all clients from resolver
            The network configuration may have changed,
            in particular when containers ared added/removed
            from docker services.

            We ask for a new updated list of servers from
            the resolver.
        """
        configs = {conf.address_to_string(): conf for conf in await self._resolver.configs}
        addresses = set(configs)

        current_addr = set(s.address for s in self._backends)

        new_addr = addresses.difference(current_addr)
        removed_addr = current_addr.difference(addresses)

        if not new_addr and not removed_addr:
            return

        def _update():
            for server in self._backends:
                if server.address in removed_addr:
                    logger.warning(
                        "Removing server at '%s' (%s)",
                        server.address,
                        self.label,
                    )
                    asyncio.create_task(server.shutdown())
                else:
                    # Keep current servers
                    yield server
            for address in new_addr:
                # Add new server
                logger.debug("Adding backend [%s] for pool %s", address, self.label)
                yield Backend(configs[address])

        # Update server list
        self._backends = list(_update())
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
                    # Resync
                    statuses = {}
                    watchers = tuple(asyncio.create_task(_watch(s)) for s in self._backends)
                    # Populate statuses
                    while len(statuses) != len(self._backends):
                        server, status = await queue.get()
                        statuses[server.address] = status

                    yield tuple(statuses.items())

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
                        if status != statuses.get(server.address):
                            statuses[server.address] = status
                            yield tuple(statuses.items())
                finally:
                    # Cancel watchers
                    for w in watchers:
                        w.cancel()
                sync.clear()
                if not self._shutdown:
                    await asyncio.sleep(RECONNECT_DELAY)

    async def stats(self) -> Sequence[Tuple[Backend, Optional[Dict]]]:
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

        return await asyncio.gather(*(_stats(s) for s in self._backends))

    async def watch_stats(
        self,
        interval: int = 3,
    ) -> AsyncIterator[Sequence[Tuple[Backend, Optional[Dict]]]]:
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
                    _watchers = tuple(s.watch_stats(interval) for s in self._backends)
                    while _watchers:
                        results = await asyncio.gather(*(anext(w) for w in _watchers))
                        yield tuple(_to_dict(item, stats) for item, stats in results)
                        if sync.is_set():
                            break
                except StopAsyncIteration:
                    # Client was shutdown
                    logger.trace("%s: client shutdown (StopAsyncIteration)", self.label)
                    pass
                sync.clear()
                if not self._shutdown:
                    await asyncio.sleep(RECONNECT_DELAY)

    #
    # Cache
    #

    async def _reduce_server_cache(self, server) -> Iterator[Tuple[str, Dict]]:
        """ Consolidate cache for client
        """
        cached_status = {}
        try:
            async for item in server.list_cache():
                status = cached_status.get(item.uri)
                if not status:
                    status = MessageToDict(item)
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
        return server.address, cached_status.values()

    async def cache_content(self) -> Dict[str, Dict[str, Dict]]:
        """ Build a synthetic/consolidated view
            of the cache contents from all
            servers in the cluster.

            Return a dict of cached status list grouped
            by project's resource.
        """
        all_status = await asyncio.gather(
            *(self._reduce_server_cache(s) for s in self._backends)
        )

        result = {}
        # Organize by cache uri
        for addr, status_list in all_status:
            for item in status_list:
                bucket = result.setdefault(item['uri'], {})
                bucket[addr] = item

        return result

    async def synchronize_cache(self) -> Dict[str, Dict[str, Dict]]:
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

        await asyncio.gather(*(_collect(s) for s in self._backends))

        result = {uri: {} for uri in uris}

        async def _reduce(server):
            try:
                async for item in server.pull_projects(*uris):
                    rv = MessageToDict(item)
                    del rv['cacheId']
                    result[item.uri][server.address] = rv
            except grpc.RpcError as err:
                if err.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.error("Server '{server.address}' is unreachable")
                else:
                    logger.error("%s\t%s\t%s", server.address, err.code(), err.details())
                    raise

        await asyncio.gather(*(_reduce(s) for s in self._backends))
        return result

    async def clear_cache(self) -> None:
        """ Clear cache for all servers
        """
        serving = False
        for server in self._backends:
            try:
                await server.clear_cache()
                serving = True
            except grpc.RpcError as err:
                if err.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.error("Server '{server.address}' is unreachable")
                else:
                    logger.error("%s\t%s\t%s", server.address, err.code(), err.details())
                    raise
        if not serving:
            raise ServiceNotAvailable(self.address)

    async def pull_projects(self, *uris) -> Dict[str, Dict[str, Dict]]:
        """ Pull/Update projects in all cache
        """
        rv = {}
        serving = False

        for server in self._backends:
            try:
                cached = {}
                async for item in server.pull_projects(*uris):
                    _item = cached.get(item.uri)
                    if not _item:
                        _item = MessageToDict(item)
                        del _item['cacheId']
                        cached[item.uri] = _item
                    else:
                        reduce_cache(_item, item)
                for uri, _item in cached.items():
                    rv.setdefault(uri, {})[server.address] = _item
                serving = True
            except grpc.RpcError as err:
                if err.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.error("Server '{server.address}' is unreachable")
                else:
                    logger.error("%s\t%s\t%s", server.address, err.code(), err.details())
                    raise

        if not serving:
            raise ServiceNotAvailable(self.address)
        return rv

    async def drop_project(self, uri: str) -> Dict[str, Dict]:
        """ Pull/Update projects in all cache
        """
        rv = {}
        serving = False
        for server in self._backends:
            try:
                _item = None
                async for item in server.drop_project(uri):
                    if not _item:
                        _item = MessageToDict(item)
                        del _item['cacheId']
                    else:
                        reduce_cache(_item, item)
                rv[server.address] = _item
                serving = True
            except grpc.RpcError as err:
                if err.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.error("Server '{server.address}' is unreachable")
                else:
                    logger.error("%s\t%s\t%s", server.address, err.code(), err.details())
                    raise

        if not serving:
            raise ServiceNotAvailable(self.address)
        return rv

    async def checkout_project(self, uri: str) -> Dict[str, Dict]:
        """ Pull/Update projects in all cache
        """
        rv = {}
        serving = False
        for server in self._backends:
            try:
                _item = None
                async for item in server.checkout_project(uri):
                    if not _item:
                        _item = MessageToDict(item)
                        del _item['cacheId']
                    else:
                        reduce_cache(_item, item)
                rv[server.address] = _item
                serving = True
            except grpc.RpcError as err:
                if err.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.error("Server '{server.address}' is unreachable")
                else:
                    logger.error("%s\t%s\t%s", server.address, err.code(), err.details())
                    raise

        if not serving:
            raise ServiceNotAvailable(self.address)
        return rv

    async def project_info(self, uri: str) -> Optional[Dict]:
        """ Pull/Update projects in all cache

            Return None if the project is not found
        """
        serving = False
        for server in self._backends:
            try:
                serving = True
                item = await server.project_info(uri)
                item = MessageToDict(item)
                item.update(serverAddress=server.address)
                return item
            except grpc.RpcError as err:
                match err.code():
                    case grpc.StatusCode.UNAVAILABLE:
                        logger.error("Server '{server.address}' is unreachable")
                    case grpc.StatusCode.NOT_FOUND:
                        pass
                    case _:
                        logger.error("%s\t%s\t%s", server.address, err.code(), err.details())
                        raise

        if not serving:
            raise ServiceNotAvailable(self.address)

    #
    # Catalog
    #

    async def catalog(self, location: Optional[str] = None) -> AsyncIterator[Dict]:
        """ Return the catalog
        """
        # Find a serving server
        # All servers share the same config so
        # find a serving to get the catalog
        for s in self._backends:
            try:
                async for item in s.catalog(location):
                    yield MessageToDict(item)
                return
            except grpc.RpcError as rpcerr:
                if rpcerr.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.debug("Server '{server.address}' is unreachable")
                    continue
                else:
                    logger.error("%s\t%s\t%s", s.address, rpcerr.code(), rpcerr.details())
                    raise
        raise ServiceNotAvailable(self.address)

    #
    # Conf
    #

    async def get_config(self, include_env: bool = False) -> Json | Tuple[Json, Json]:
        """ Return the configuration
        """
        # Find a serving server
        # All servers share the same config
        serving = False
        for s in self._backends:
            try:
                if include_env:
                    async with s._stub(None):
                        return (
                            await s.get_config(),
                            await s.get_env(),
                        )
                else:
                    return await s.get_config()
                serving = True
            except grpc.RpcError as rpcerr:
                if rpcerr.code() == grpc.StatusCode.UNAVAILABLE:
                    continue
                else:
                    logger.error("%s\t%s\t%s", s.address, rpcerr.code(), rpcerr.details())
                    raise
        if not serving:
            raise ServiceNotAvailable(self.address)

    async def set_config(self, conf: Dict, return_diff: bool = False) -> Optional[Json]:
        """ Change backends configuration
            and return diff between current and new config
        """
        # All servers share the same config
        serving = False
        diff_conf = None
        for s in self._backends:
            try:
                if return_diff:
                    async with s._stub(None):
                        prev_conf = json.loads(await s.get_config())
                        await s.set_config(conf)
                        new_conf = json.loads(await s.get_config())
                        diff_conf = json.dumps(jsondiff.diff(prev_conf, new_conf, syntax='symmetric'))
                        return_diff = False  # Only need to make it once
                else:
                    await s.set_config(conf)

                serving = True
            except grpc.RpcError as rpcerr:
                match rpcerr.code():
                    case grpc.StatusCode.UNAVAILABLE:
                        logger.warning(
                            "%s UNAVAILABLE, configuration may be unsync at some time",
                            s.address,
                        )
                        continue
                    case grpc.StatusCode.INVALID_ARGUMENT:
                        raise RequestArgumentError(rpcerr.details()) from None
                    case _:
                        logger.error("%s\t%s\t%s", s.address, rpcerr.code(), rpcerr.details())
                        raise
        if not serving:
            raise ServiceNotAvailable(self.address)

        return diff_conf

    #
    # Plugins
    #

    async def list_plugins(self) -> List[Dict]:
        """ Pull/Update projects in all cache
        """
        plugins = {}
        serving = False
        for server in self._backends:
            try:
                async for item in server.list_plugins():
                    _item = plugins.get(item.name)
                    if not _item:
                        _item = MessageToDict(item)
                        _item['backends'] = [server.address]
                        plugins[item.name] = _item
                    else:
                        _item['backends'].append(server.address)
                serving = True
            except grpc.RpcError as err:
                if err.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.error("Server '{server.address}' is unreachable")
                else:
                    logger.error("%s\t%s\t%s", server.address, err.code(), err.details())
                    raise

        if not serving:
            raise ServiceNotAvailable(self.address)
        return list(plugins.values())
