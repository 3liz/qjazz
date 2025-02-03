import asyncio
import json
import traceback

from contextlib import contextmanager
from typing import (
    AsyncIterator,
    Dict,
    Generator,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
)

import grpc
import jsondiff

from google.protobuf import json_format
from google.protobuf.message import Message
from pydantic import Json, JsonValue

from qjazz_contrib.core import logger
from qjazz_rpc._grpc import qjazz_pb2

from .backend import RECONNECT_DELAY, Backend
from .errors import RequestArgumentError, ServiceNotAvailable
from .resolvers import Resolver


def MessageToDict(message: Message) -> Dict[str, JsonValue]:
    return json_format.MessageToDict(
        message,
        # including_default_value_fields=True,
        # XXX Since protobuf 5.26
        # See https://github.com/python/typeshed/issues/11636
        always_print_fields_with_no_presence=True,  # type: ignore [call-arg]
        preserving_proto_field_name=False,
    )


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
        self._backends: List[Backend] = []
        self._shutdown = False
        self._sync_events: Tuple[asyncio.Event, ...] = ()

    def __len__(self):
        return len(self._backends)

    @property
    def label(self) -> str:
        return self._resolver.label

    @property
    def address(self) -> str:
        return self._resolver.resolver_address()

    @property
    def title(self) -> str:
        return self._resolver.title

    @property
    def description(self) -> Optional[str]:
        return self._resolver.description

    async def shutdown(self):
        self._shutdown = True
        self._sync()
        for s in self._backends:
            await s.shutdown()

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
            self._sync_events = tuple(e for e in evts if e is not event)  # type: ignore

    def _sync(self):
        """ Set all synchronization events
        """
        for evt in self._sync_events:
            evt.set()

    @property
    def backends(self) -> Iterator[Backend]:
        for server in self._backends:
            yield server

    async def enable_backends(self, enable: bool):
        for s in self._backends:
            await s.enable_server(enable)

    async def update_backends(self) -> None:
        """ Set up all clients from resolver
            The network configuration may have changed,
            in particular when containers ared added/removed
            from docker services.

            We ask for a new updated list of servers from
            the resolver.
        """
        # Get backends from resolvers
        configs = {conf.address_to_string(): conf for conf in await self._resolver.backends}
        addresses = set(configs)

        # Current backends
        current_addr = set(s.address for s in self._backends)

        new_addr = addresses.difference(current_addr)
        removed_addr = current_addr.difference(addresses)

        if not new_addr and not removed_addr:
            return

        def _update():
            background_tasks = set()
            for server in self._backends:
                if server.address in removed_addr:
                    logger.warning(
                        "Removing server at '%s' (%s)",
                        server.address,
                        self.label,
                    )
                    # See https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
                    # why we need to keep task reference
                    task = asyncio.create_task(server.shutdown())
                    background_tasks.add(task)
                    task.add_done_callback(background_tasks.discard)
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
        queue: asyncio.Queue[Tuple[Backend, bool]] = asyncio.Queue()
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
                    statuses: Dict[str, bool] = {}
                    watchers = tuple(asyncio.create_task(_watch(s)) for s in self._backends)
                    # Populate statuses
                    while len(statuses) != len(self._backends):
                        server, status = await queue.get()
                        statuses[server.address] = status

                    yield tuple(statuses.items())

                    while watchers:
                        done, pending = await asyncio.wait(
                            (
                                asyncio.create_task(sync.wait()),
                                asyncio.create_task(queue.get()),
                            ),
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
                        server, status = done.pop().result()  # type: ignore
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
                    watchers = tuple(s.watch_stats(interval) for s in self._backends)
                    while watchers:
                        results = await asyncio.gather(*(anext(w) for w in watchers))
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

    async def cache_content(self) -> Dict[str, Dict[str, qjazz_pb2.CacheInfo]]:
        """ Build view of the cache contents by
            servers in the cluster.

            Return a dict of cached status list grouped
            by project's resource.
        """
        rv: Dict[str, Dict[str, qjazz_pb2.CacheInfo]] = {}
        serving = False
        try:
            for server in self._backends:
                async for item in server.list_cache():
                    rv.setdefault(item.uri, {})[server.address] = item
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

    async def synchronize_cache(self) -> Dict[str, Dict[str, qjazz_pb2.CacheInfo]]:
        """ Synchronize backends caches
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
                    rpcerr.details(),
                )

        # Collect cache for each backends
        await asyncio.gather(*(_collect(s) for s in self._backends))

        result: Dict[str, Dict[str, qjazz_pb2.CacheInfo]] = {uri: {} for uri in uris}

        async def _pull(server):
            try:
                async for item in server.pull_projects(*uris):
                    result[item.uri][server.address] = item
            except grpc.RpcError as err:
                if err.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.error("Server '{server.address}' is unreachable")
                else:
                    logger.error("%s\t%s\t%s", server.address, err.code(), err.details())
                    raise

        await asyncio.gather(*(_pull(s) for s in self._backends))
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

    async def pull_projects(self, *uris) -> Dict[str, Dict[str, qjazz_pb2.CacheInfo]]:
        """ Pull/Update projects in all cache
        """
        rv: Dict[str, Dict[str, qjazz_pb2.CacheInfo]] = {}
        serving = False

        for server in self._backends:
            try:
                async for item in server.pull_projects(*uris):
                    rv.setdefault(item.uri, {})[server.address] = item
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

    async def drop_project(self, uri: str) -> Dict[str, qjazz_pb2.CacheInfo]:
        """ Pull/Update projects in all cache
        """
        rv = {}
        serving = False
        for server in self._backends:
            try:
                item = await server.drop_project(uri)
                rv[server.address] = item
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

    async def checkout_project(self, uri: str) -> Dict[str, qjazz_pb2.CacheInfo]:
        """ Pull/Update projects in all cache
        """
        rv = {}
        serving = False
        for server in self._backends:
            try:
                rv[server.address] = await server.checkout_project(uri)
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

    async def project_info(self, uri: str) -> Optional[Dict[str, JsonValue]]:
        """ Pull/Update projects in all cache

            Return None if the project is not found
        """
        serving = False
        for server in self._backends:
            try:
                serving = True
                item = MessageToDict(await server.project_info(uri))
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
        return None  # Makes mypy happy

    #
    # Catalog
    #

    async def catalog(
        self,
        location: Optional[str] = None,
    ) -> AsyncIterator[qjazz_pb2.CatalogItem]:
        """ Return the catalog
        """
        # Find a serving server
        # All servers share the same config so
        # find a serving to get the catalog
        for s in self._backends:
            try:
                async for item in s.catalog(location):
                    yield item
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
                    async with s.connection():
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
        return None  # Make mypy happy

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
                    async with s.connection():
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

    async def list_plugins(self) -> Dict[str, List[qjazz_pb2.PluginInfo]]:
        """ Pull/Update projects in all cache
        """
        plugins: Dict[str, List[qjazz_pb2.PluginInfo]] = {}
        serving = False

        for server in self._backends:
            try:
                plugins[server.address] = [item async for item in server.list_plugins()]
                serving = True
            except grpc.RpcError as err:
                if err.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.error("Server '{server.address}' is unreachable")
                else:
                    logger.error("%s\t%s\t%s", server.address, err.code(), err.details())
                    raise

        if not serving:
            raise ServiceNotAvailable(self.address)
        return plugins
