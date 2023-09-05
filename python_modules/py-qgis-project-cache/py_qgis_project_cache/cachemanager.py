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
    CacheManager.initialize_handlers()

    cm = CacheManager()
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

    # Update the catalog according to
    # the returned status
    entry = cm.update(md, status)

    myproject = entry.project
    ```

"""
import traceback

from typing import Tuple, Optional, Iterator
from pathlib import Path
from enum import Enum
from dataclasses import dataclass

from qgis.core import QgsProject

from py_qgis_contrib.core import (
    componentmanager,
    logger,
)

# Import default handlers for auto-registration
from .common import Url, IProtocolHandler
from .handlers import init_storage_handlers
from .storage import ProjectMetadata, StrictCheckingFailure
from .config import ProjectsConfig

CACHE_MANAGER_CONTRACTID = '@3liz.org/cache-manager;1'


class ResourceNotAllowed(Exception):
    pass


class UnreadableResource(Exception):
    """ Indicates that the  ressource exists but is not readable
    """
    pass


@dataclass(frozen=True)
class CatalogEntry:
    md: ProjectMetadata
    project: QgsProject

    # Delegate to ProjectMetadata
    def __getattr__(self, attr):
        return self.md.__getattribute__(attr)


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
    # Not returned as cache status by the CacheManager
    # but may by used to be aware that a resource
    # has been updated at request time (i.e update from
    # NEEDUPDATE status)
    UPDATED = 5


@componentmanager.register_factory(CACHE_MANAGER_CONTRACTID)
class CacheManager:
    """ Handle Qgis project cache
    """

    StrictCheckingFailure = StrictCheckingFailure
    ResourceNotAllowed = ResourceNotAllowed
    UnreadableResource = UnreadableResource
    CheckoutStatus = CheckoutStatus

    @classmethod
    def initialize_handlers(cls, confdir: Optional[Path] = None):
        # Register Qgis storage handlers
        init_storage_handlers(confdir)
        # Load protocol handlers
        componentmanager.register_entrypoints('py_qgis_contrib_protocol_handler')

    def __init__(self, config: ProjectsConfig) -> None:
        self._config = config
        self._catalog = {}

    @property
    def conf(self) -> str:
        """ Return the current configuration
        """
        return self._config

    def resolve_path(self, path: str, allow_direct: bool = False) -> Url:
        """ Resolve path according to location mapping

            `path` is translated to an url corresponding to
            a potential storage backend (i.e `file`, `postgresql` ...)

            if `allow_direct_path_resolution` configuration is set to true,
            unresolved path are passed 'as is' and will
            be directly interpreted by the protocol handler
            corresponding to the url's scheme.
        """
        path = Path(path)
        # Find matching path
        for location, rooturl in self.conf.search_paths.items():
            if path.is_relative_to(location):
                path = path.relative_to(location)
                url = rooturl._replace(path=str(Path(rooturl.path, path)))
                return url

        if allow_direct or self.conf.allow_direct_path_resolution:
            # Use direct resolution based on scheme
            return url
        else:
            raise ResourceNotAllowed(path)

    def get_protocol_handler(self, scheme: str) -> IProtocolHandler:
        """ Find protocol handler for the given scheme
        """
        return componentmanager.get_service(
            f'@3liz.org/cache/protocol-handler;1?scheme={scheme}'
        )

    def collect_projects(self) -> Iterator[ProjectMetadata]:
        """ Collect projects metadata from search paths

            Yield found entries
        """
        for url in self.conf.search_paths.values():
            try:
                handler = self.get_protocol_handler(url.scheme)
                yield from handler.projects(url)
            except Exception:
                logger.error(traceback.format_exc())

    def checkout(self, url: Url) -> Tuple[Optional[ProjectMetadata | CatalogEntry], CheckoutStatus]:
        """ Checkout status of project from url

            Returned status:
            * `NEW`: Project exists but is not loaded
            * `NEEDUPDATE`: Project is loaded and is out of date
            * `REMOVED`: Project is loaded but was removed from storage
            * `UNCHANGED`: Project is loaded and is up to date
            * `NOTFOUND` : Project does not exist in storage

            Possible return values are:
            - `(CatalogEntry, CheckoutStatus.NEEDUPDATE)`
            - `(CatalogEntry, CheckoutStatus.UNCHANGED)`
            - `(CatalogEntry, CheckoutStatus.REMOVED)`
            - `(ProjectMetadata, CheckoutStatus.NEW)`
            - `(None, CheckoutStatus.NOTFOUND)`
        """
        handler = self.get_protocol_handler(url.scheme)
        try:
            md = handler.project_metadata(url)
            e = self._catalog.get(md.uri)
            if e:
                if md.last_modified > e.md.last_modified:
                    retval = (e, CheckoutStatus.NEEDUPDATE)
                else:
                    retval = (e, CheckoutStatus.UNCHANGED)
            else:
                retval = (md, CheckoutStatus.NEW)
        except FileNotFoundError as err:
            # The argument is the resolved uri
            e = self._catalog.get(err.args[0])
            if e:
                retval = (e, CheckoutStatus.REMOVED)
            else:
                retval = (None, CheckoutStatus.NOTFOUND)

        return retval

    def peek(self, url: Url) -> Optional[CatalogEntry]:
        """ Peek an entry from the the catalog

            Return None if the entry does not exists
        """
        handler = self.get_protocol_handler(url.scheme)
        return self._catalog.get(handler.resolve_uri(url))

    def update(
        self,
        md: ProjectMetadata,
        status: CheckoutStatus,
        handler: Optional[IProtocolHandler] = None,
    ) -> Optional[CatalogEntry]:
        """ Update catalog entry according to status

            * `NEW`: (re)load existing project
            * `NEEDUPDATE`: update loaded project
            * `REMOVED`: remove loaded project
            * `UNCHANGED`: do nothing
            * `NOTFOUND` : do nothing

            If the status is NOTFOUND then return None

            In all other cases the entry *must* exists in
            the catalog or an exception is raised
        """
        match status:
            case CheckoutStatus.NEW:
                logger.debug("Adding new entry '%s'", md.uri)
                handler = handler or self.get_protocol_handler(md.scheme)
                entry = CatalogEntry(md, handler.project(md, self.conf))
                self._catalog[md.uri] = entry
                return entry
            case CheckoutStatus.NEEDUPDATE:
                entry = self._catalog[md.uri]
                if md.modified_time > entry.md.modified_time:
                    logger.debug("Updating entry '%s'", md.uri)
                    handler = handler or self.get_protocol_handler(md.scheme)
                    entry = CatalogEntry(md, handler.project(md, self.conf))
                    self._catalog[md.uri] = entry
                return entry
            case CheckoutStatus.UNCHANGED:
                return self._catalog[md.uri]
            case CheckoutStatus.REMOVED:
                logger.debug("Removing entry '%s'", md.uri)
                return self._catalog.pop(md.uri)

    def update_catalog(self) -> Iterator[CatalogEntry]:
        """ Update all entries in catalog

            Yield updated catalog entries
        """
        for e in self._catalog.values():
            handler = self.get_protocol_handler(e.md.scheme)
            try:
                md = handler.project_metadata(e.md)
                if md.modified_time > e.md.modified_time:
                    yield self.update(md, CheckoutStatus.NEEDUPDATE, handler)
            except FileNotFoundError:
                self.update(e.md, CheckoutStatus.REMOVED, handler)
                yield e

    def clear(self) -> None:
        """ Clear all projects
        """
        self._catalog.clear()

    def iter(self) -> Iterator[CatalogEntry]:
        """ Iterate over all catalog entries
        """
        return self._catalog.values()

    @property
    def size(self) -> int:
        """ Return the number of entries in
            the catalog
        """
        return len(self._catalog)
