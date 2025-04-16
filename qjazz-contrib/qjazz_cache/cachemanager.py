#
# Copyright 2020-2023 3liz
# Author David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Cache manager for Qgis Projects

Usage example

.. code-block:: python

    cm = CacheManager(conf)
    # Resolve location
    url = cm.resolve_path("/my/project")

    # Check status
    md, status = cm.checkout(url)

    match status:
        case CheckoutStatus.NEW:
            print("Project exists and is not loaded")
        case CheckoutStatus.NEEDUPDATE:
            print("Project is already loaded and need to be updated")
        case CheckoutStatus.UNCHANGED:
            print("Project is loaded and is up to date")
        case CheckoutStatus.REMOVED:
            print("Project is loaded but has been removed from storage")
        case CheckoutStatus.NOTFOUND:
            print("Project does not exists")

    # Update the cache according to
    # the returned status
    entry, update_status = cm.update(md, status)

    myproject = entry.project

"""

import traceback

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

from dataclasses import dataclass
from pathlib import PurePosixPath
from time import time
from typing import (
    Iterable,
    Iterator,
    Optional,
    Self,
    assert_never,
)

from qgis.core import QgsProject
from qgis.server import QgsServer

from qjazz_contrib.core import componentmanager, logger

# Import default handlers for auto-registration
from .common import ProjectMetadata, ProtocolHandler, Url
from .config import ProjectsConfig
from .errors import (
    ResourceNotAllowed,
    StrictCheckingFailure,
    UnreadableResource,
)
from .handlers import (
    register_default_handlers,
    register_protocol_handler,
)
from .routes import validate_url
from .status import CheckoutStatus

CACHE_MANAGER_CONTRACTID = "@3liz.org/cache-manager;1"


@dataclass(frozen=True)
class DebugMetadata:
    load_memory_bytes: Optional[int]
    load_time_ms: int


@dataclass(frozen=True)
class CacheEntry:
    md: ProjectMetadata
    project: QgsProject
    timestamp: float

    debug_meta: DebugMetadata

    last_hit: float = 0.0
    hits: int = 0
    pinned: bool = False

    # Delegate to ProjectMetadata
    def __getattr__(self, attr):
        return self.md.__getattribute__(attr)

    # Increase the number of hits
    def hit_me(self):
        # Get around frozen
        self.__dict__["hits"] += 1
        self.__dict__["last_hit"] = time()

    def pin(self):
        self.__dict__["pinned"] = True


class CacheManager:
    """Handle Qgis project cache"""

    StrictCheckingFailure = StrictCheckingFailure
    ResourceNotAllowed = ResourceNotAllowed
    UnreadableResource = UnreadableResource

    @classmethod
    def initialize_handlers(cls, config: ProjectsConfig):
        """Register handlers to component manager"""
        register_default_handlers()
        for scheme, conf in config.handlers.items():
            register_protocol_handler(scheme, conf)

        # Validate rooturls
        for route in config.search_paths.routes:
            path, rooturl = route.cannonical
            if logger.is_enabled_for(logger.LogLevel.DEBUG):
                logger.debug("Validating cache root url '%s' (path: '%s')", rooturl.geturl(), path)
            handler = cls.get_protocol_handler(rooturl.scheme)
            handler.validate_rooturl(rooturl, config, route.is_dynamic)

    @classmethod
    def get_service(cls) -> Self:
        """Return cache manager as a service.
        This require that register_as_service has been called
        in the current context
        """
        return componentmanager.get_service(CACHE_MANAGER_CONTRACTID)

    @classmethod
    def get_protocol_handler(cls, scheme: str) -> ProtocolHandler:
        """Find protocol handler for the given scheme"""
        return componentmanager.get_service(
            f"@3liz.org/cache/protocol-handler;1?scheme={scheme}",
        )

    def __init__(
        self,
        config: ProjectsConfig,
        server: Optional[QgsServer] = None,
    ) -> None:
        self._config = config
        self._cache: dict[str, CacheEntry] = {}
        # For debug metadata
        self._process = psutil.Process() if psutil else None
        self._server = server

    def register_as_service(self):
        componentmanager.register_service(CACHE_MANAGER_CONTRACTID, self)

    @property
    def conf(self) -> ProjectsConfig:
        """Return the current configuration"""
        return self._config

    def resolve_path(self, path: str, allow_direct: bool = False) -> Url:
        """Resolve path according to location mapping

        `path` is translated to an url corresponding to
        a potential storage backend (i.e `file`, `postgresql` ...)

        if `allow_direct_path_resolution` configuration is set to true,
        unresolved path are passed 'as is' and will
        be directly interpreted by the protocol handler
        corresponding to the url's scheme.

        If the root url have '{path}' template pattern in the query
        the it will be replaced by the relative path from the input.

        Otherwise it will simply be appended to the root url path.
        """
        path = PurePosixPath(path)
        # Find matching path
        for route in self.conf.search_paths.routes:
            result = route.resolve_path(path)
            if not result:
                continue

            location, rooturl = result
            path = path.relative_to(location)

            # Check for {path} template in rooturl
            query = rooturl.query.format(path=path)
            if query != rooturl.query:
                url = rooturl._replace(query=query)
            else:
                # Simply append path to the rooturl path
                url = rooturl._replace(path=str(PurePosixPath(rooturl.path, path)))

            return url

        if allow_direct or self.conf.allow_direct_path_resolution:
            # Use direct resolution based on scheme
            return validate_url(str(path))
        else:
            raise ResourceNotAllowed(str(path))


    def locations(self, location: Optional[str] = None) -> Iterable[tuple[str, Url]]:
        """List compatible search paths"""
        return self.conf.search_paths.locations(location)

    def collect_projects_ex(
        self,
        location: Optional[str] = None,
    ) -> Iterator[tuple[ProjectMetadata, str, ProtocolHandler, PurePosixPath]]:
        """Collect projects metadata from search paths

        Yield tuple of (entry, public_path, handler) for all found  entries
        """
        for location, url in self.locations(location):
            try:
                loc = PurePosixPath(location) 
                handler = self.get_protocol_handler(url.scheme)
                for md in handler.projects(url):
                    yield md, handler.public_path(md.uri, location, url), handler, loc
            except Exception:
                logger.error(traceback.format_exc())

    def collect_projects(
        self,
        location: Optional[str] = None,
    ) -> Iterator[tuple[ProjectMetadata, str]]:
        """Collect projects metadata from search paths

        Yield tuple of (entry, public_path) for all found  entries
        """
        for md, public_path, _, _ in self.collect_projects_ex(location):
            yield md, public_path

    def checkout(self, url: Url) -> tuple[Optional[ProjectMetadata | CacheEntry], CheckoutStatus]:
        """Checkout status of project from url

        Returned status:
        * `NEW`: Project exists but is not loaded
        * `NEEDUPDATE`: Project is loaded and is out of date
        * `REMOVED`: Project is loaded but was removed from storage
        * `UNCHANGED`: Project is loaded and is up to date
        * `NOTFOUND` : Project does not exist in storage

        Possible return values are:
        - `(CacheEntry, CheckoutStatus.NEEDUPDATE)`
        - `(CacheEntry, CheckoutStatus.UNCHANGED)`
        - `(CacheEntry, CheckoutStatus.REMOVED)`
        - `(ProjectMetadata, CheckoutStatus.NEW)`
        - `(None, CheckoutStatus.NOTFOUND)`
        """
        retval: tuple[Optional[ProjectMetadata | CacheEntry], CheckoutStatus]
        handler = self.get_protocol_handler(url.scheme)
        try:
            md = handler.project_metadata(url)
            e = self._cache.get(md.uri)
            if e:
                if md.last_modified > e.md.last_modified:
                    retval = (e, CheckoutStatus.NEEDUPDATE)
                else:
                    retval = (e, CheckoutStatus.UNCHANGED)
            else:
                retval = (md, CheckoutStatus.NEW)
        except FileNotFoundError as err:
            # The argument is the resolved uri
            e = self._cache.get(err.args[0])
            if e:
                retval = (e, CheckoutStatus.REMOVED)
            else:
                retval = (None, CheckoutStatus.NOTFOUND)

        return retval

    def checkout_entry(self, entry: CacheEntry) -> tuple[CacheEntry, CheckoutStatus]:
        """Checkout from existing entry"""
        handler = self.get_protocol_handler(entry.scheme)
        try:
            md = handler.project_metadata(validate_url(entry.uri))
            if md.last_modified > entry.md.last_modified:
                retval = (entry, CheckoutStatus.NEEDUPDATE)
            else:
                retval = (entry, CheckoutStatus.UNCHANGED)
        except FileNotFoundError:
            retval = (entry, CheckoutStatus.REMOVED)

        return retval

    def update(
        self,
        md: ProjectMetadata,
        status: CheckoutStatus,
        handler: Optional[ProtocolHandler] = None,
    ) -> tuple[CacheEntry, CheckoutStatus]:
        """Update cache entry according to status

        * `NEW`: (re)load existing project
        * `NEEDUPDATE`: update loaded project
        * `REMOVED`: remove loaded project
        * `UNCHANGED`: do nothing
        * `NOTFOUND` : do nothing

        If the status is NOTFOUND then return None

        In all other cases the entry *must* exists in
        the cache or an exception is raised
        """
        match status:
            case CheckoutStatus.NEW:
                logger.debug("CACHE UPDATE: Adding new entry '%s'", md.uri)
                handler = handler or self.get_protocol_handler(md.scheme)
                entry = self._new_cache_entry(md, handler)
                self._cache[md.uri] = entry
                return entry, status
            case CheckoutStatus.NEEDUPDATE:
                logger.debug("CACHE UPDATE: Updating entry '%s'", md.uri)
                handler = handler or self.get_protocol_handler(md.scheme)
                self._delete_cache_entry(md)
                # Insert new entry
                entry = self._new_cache_entry(md, handler)
                self._cache[md.uri] = entry
                return entry, CheckoutStatus.UPDATED
            case CheckoutStatus.UNCHANGED | CheckoutStatus.UPDATED:
                return self._cache[md.uri], status
            case CheckoutStatus.REMOVED:
                logger.debug("CACHE UPDATE: Removing entry '%s'", md.uri)
                entry = self._delete_cache_entry(md)
                return entry, status
            case CheckoutStatus.NOTFOUND:
                raise ValueError(f"Invalid CheckoutStatus value for update(): {status}")
            case _ as unreachable:
                assert_never(unreachable)

    def _new_cache_entry(
        self,
        md: ProjectMetadata,
        handler: ProtocolHandler,
    ) -> CacheEntry:
        """Create a new cache entry"""
        s_time = time()
        s_mem = self._process.memory_info().rss if self._process else None

        project = handler.project(md, self.conf)

        # Prevent circular ownership
        if isinstance(md, CacheEntry):
            last_used_mem = md.debug_meta.load_memory_bytes
            md = md.md
        else:
            last_used_mem = 0
        #
        # This is a best effort to get meaningful information
        # about how memory is used by a project. So we
        # keep with last mesured footprint in case of reloading
        # a project:
        #
        used_mem = self._process.memory_info().rss - s_mem if self._process else None
        if used_mem is not None and used_mem < last_used_mem:
            used_mem = last_used_mem

        return CacheEntry(
            md,
            project,
            timestamp=time(),
            debug_meta=DebugMetadata(
                load_memory_bytes=used_mem,
                load_time_ms=int((time() - s_time) * 1000.0),
            ),
        )

    def update_cache(self) -> Iterator[tuple[CacheEntry, CheckoutStatus]]:
        """Update all entries in cache

        Yield updated cache entries
        """
        for e in self._cache.values():
            handler = self.get_protocol_handler(e.md.scheme)
            try:
                md = handler.project_metadata(e.md)
                if md.last_modified > e.md.last_modified:
                    yield self.update(md, CheckoutStatus.NEEDUPDATE, handler)
                else:
                    yield (e, CheckoutStatus.UNCHANGED)
            except FileNotFoundError:
                yield self.update(e.md, CheckoutStatus.REMOVED, handler)

    def clear(self) -> None:
        """Clear all projects"""
        if self._server:
            iface = self._server.serverInterface()
            for e in self._cache.values():
                path = e.project.fileName()
                logger.trace(">> Removing server config cache for %s", path)
                iface.removeConfigCacheEntry(e.project.fileName())

        self._cache.clear()

    def iter(self) -> Iterator[CacheEntry]:
        """Iterate over all cache entries"""
        return iter(self._cache.values())

    def checkout_iter(self) -> Iterator[tuple[CacheEntry, CheckoutStatus]]:
        """Iterate and checkout over all cache entries"""
        return (self.checkout_entry(e) for e in self.iter())

    def __len__(self) -> int:
        """Return the number of entries in
        the cache
        """
        return len(self._cache)

    def _delete_cache_entry(self, md: ProjectMetadata) -> CacheEntry:
        """Update the server cache"""
        entry = self._cache.pop(md.uri)
        if self._server:
            # Update server cache
            path = entry.project.fileName()
            logger.trace("Removing Qgis cache for %s", path)
            iface = self._server.serverInterface()
            iface.removeConfigCacheEntry(path)
        return entry
