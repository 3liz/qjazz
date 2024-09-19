#
# Copyright 2020-2023 3liz
# Author David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

""" Cache manager for Qgis Projects

    Usage example
    ```
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
    ```

"""
import traceback

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from time import time

from typing_extensions import (
    Dict,
    Iterable,
    Iterator,
    Optional,
    Self,
    Tuple,
    assert_never,
)

from qgis.core import QgsProject
from qgis.server import QgsServer

from py_qgis_contrib.core import componentmanager, logger

# Import default handlers for auto-registration
from .common import ProjectMetadata, ProtocolHandler, Url
from .config import ProjectsConfig, validate_url
from .errors import (
    ResourceNotAllowed,
    StrictCheckingFailure,
    UnreadableResource,
)
from .handlers import (
    register_default_handlers,
    register_protocol_handler,
)

CACHE_MANAGER_CONTRACTID = '@3liz.org/cache-manager;1'


@dataclass(frozen=True)
class DebugMetadata:
    load_memory_bytes: int
    load_time_ms: int


@dataclass(frozen=True)
class CacheEntry:
    md: ProjectMetadata
    project: QgsProject
    timestamp: float

    debug_meta: DebugMetadata

    last_hit: float = 0.
    hits: int = 0
    pinned: bool = False

    # Delegate to ProjectMetadata
    def __getattr__(self, attr):
        return self.md.__getattribute__(attr)

    # Increase the number of hits
    def hit_me(self):
        # Get around frozen
        self.__dict__['hits'] += 1
        self.__dict__['last_hit'] = time()

    def pin(self):
        self.__dict__['pinned'] = True


class CheckoutStatus(Enum):
    """ Returned as checkout result from
        CacheManager.
        Gives information about the status
        of the required resource.
    """
    UNCHANGED = 0
    NEEDUPDATE = 1
    REMOVED = 2
    NOTFOUND = 3
    NEW = 4
    # Returned by update() if the resource
    # has been updated on NEEDUPDATE.
    UPDATED = 5


class CacheManager:
    """ Handle Qgis project cache
    """
    StrictCheckingFailure = StrictCheckingFailure
    ResourceNotAllowed = ResourceNotAllowed
    UnreadableResource = UnreadableResource

    @classmethod
    def initialize_handlers(cls, config: ProjectsConfig):
        """ Register handlers to component manager
        """
        register_default_handlers()
        for scheme, conf in config.handlers.items():
            register_protocol_handler(scheme, conf)

        # Validate rooturls
        for _, rooturl in config.search_paths.items():
            handler = cls.get_protocol_handler(rooturl.scheme)
            handler.validate_rooturl(rooturl)

    @classmethod
    def get_service(cls) -> Self:
        """ Return cache manager as a service.
            This require that register_as_service has been called
            in the current context
        """
        return componentmanager.get_service(CACHE_MANAGER_CONTRACTID)

    @classmethod
    def get_protocol_handler(cls, scheme: str) -> ProtocolHandler:
        """ Find protocol handler for the given scheme
        """
        return componentmanager.get_service(
            f'@3liz.org/cache/protocol-handler;1?scheme={scheme}',
        )

    def __init__(
            self,
            config: ProjectsConfig,
            server: Optional[QgsServer] = None,
    ) -> None:
        self._config = config
        self._cache: Dict[str, CacheEntry] = {}
        # For debug metadata
        self._process = psutil.Process() if psutil else None
        self._server = server

    def register_as_service(self):
        componentmanager.register_service(CACHE_MANAGER_CONTRACTID, self)

    @property
    def conf(self) -> ProjectsConfig:
        """ Return the current configuration
        """
        return self._config

    def search_paths(self) -> Iterator[str]:
        """ Return the list of search paths
        """
        return iter(self.conf.search_paths.keys())

    def resolve_path(self, path: str, allow_direct: bool = False) -> Url:
        """ Resolve path according to location mapping

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
        path = Path(path)
        # Find matching path
        for location, rooturl in self.conf.search_paths.items():
            if path.is_relative_to(location):
                path = path.relative_to(location)

                # Check for {path} template in rooturl
                query = rooturl.query.format(path=path)
                if query != rooturl.query:
                    url = rooturl._replace(query=query)
                else:
                    # Simply append path to the rooturl path
                    url = rooturl._replace(path=str(Path(rooturl.path, path)))

                return url

        if allow_direct or self.conf.allow_direct_path_resolution:
            # Use direct resolution based on scheme
            return validate_url(str(path))
        else:
            raise ResourceNotAllowed(str(path))

    def collect_projects(self, location: Optional[str] = None) -> Iterator[Tuple[ProjectMetadata, str]]:
        """ Collect projects metadata from search paths

            Yield tuple of (entry, public_path) for all found  entries
        """
        urls: Iterable[Tuple[str, Url]]
        if location:
            url = self.conf.search_paths.get(location)
            if not url:
                logger.error(f"Location '{location}' does not exists in search paths")
                return
            else:
                urls = ((location, url),)
        else:
            urls = self.conf.search_paths.items()
        for location, url in urls:
            try:
                handler = self.get_protocol_handler(url.scheme)
                for md in handler.projects(url):
                    yield md, handler.public_path(md.uri, location, url)
            except Exception:
                logger.error(traceback.format_exc())

    def checkout(self, url: Url) -> Tuple[Optional[ProjectMetadata | CacheEntry], CheckoutStatus]:
        """ Checkout status of project from url

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
        retval: Tuple[Optional[ProjectMetadata | CacheEntry], CheckoutStatus]
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

    def checkout_entry(self, entry: CacheEntry) -> Tuple[CacheEntry, CheckoutStatus]:
        """ Checkout from existing entry
        """
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
    ) -> Tuple[CacheEntry, CheckoutStatus]:
        """ Update cache entry according to status

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
        """ Create a new cache entry
        """
        s_time = time()
        s_mem = self._process.memory_info().vms if self._process else None

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
        # a project
        #
        used_mem = self._process.memory_info().vms - s_mem if self._process else None
        if used_mem < last_used_mem:
            used_mem = last_used_mem

        return CacheEntry(
            md,
            project,
            timestamp=time(),
            debug_meta=DebugMetadata(
                load_memory_bytes=used_mem,
                load_time_ms=int((time() - s_time) * 1000.),
            ),
        )

    def update_cache(self) -> Iterator[Tuple[CacheEntry, CheckoutStatus]]:
        """ Update all entries in cache

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
        """ Clear all projects
        """
        if self._server:
            iface = self._server.serverInterface()
            for e in self._cache.values():
                path = e.project.fileName()
                logger.trace(">> Removing server config cache for %s", path)
                iface.removeConfigCacheEntry(e.project.fileName())

        self._cache.clear()

    def iter(self) -> Iterator[CacheEntry]:
        """ Iterate over all cache entries
        """
        return iter(self._cache.values())

    def checkout_iter(self) -> Iterator[Tuple[CacheEntry, CheckoutStatus]]:
        """ Iterate and checkout over all cache entries
        """
        return (self.checkout_entry(e) for e in self.iter())

    def __len__(self) -> int:
        """ Return the number of entries in
            the cache
        """
        return len(self._cache)

    def _delete_cache_entry(self, md: ProjectMetadata) -> CacheEntry:
        """ Update the server cache
        """
        entry = self._cache.pop(md.uri)
        if self._server:
            # Update server cache
            path = entry.project.fileName()
            logger.trace("Removing Qgis cache for %s", path)
            iface = self._server.serverInterface()
            iface.removeConfigCacheEntry(path)
        return entry
