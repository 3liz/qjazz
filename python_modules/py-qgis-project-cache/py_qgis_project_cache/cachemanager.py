#
# Copyright 2020-2023 3liz
# Author David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

""" Cache manager for Qgis Projects
"""
import traceback

from typing import Tuple, Optional, NamedTuple, Generator
from pathlib import Path
from enum import Enum

from qgis.core import QgsProject

from py_qgis_contrib.core import (
    componentmanager,
    logger,
    confservice,
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


class CatalogEntry(NamedTuple):
    md: ProjectMetadata
    project: Optional[QgsProject] = None


class CheckoutStatus(Enum):
    UNCHANGED = 0
    UPDATED = 1
    NEW = 2


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

    def __init__(self, config: Optional[ProjectsConfig] = None) -> None:
        self._local_config = config
        self._catalog = {}

    @property
    def conf(self) -> str:
        return self._local_config or confservice.conf.projects

    def resolve_path(self, path: str) -> Url:
        """ Resolve path
        """
        path = Path(path)
        # Find matching path
        for location, rooturl in self.conf.search_paths.items():
            if path.is_relative_to(location):
                path = path.relative_to(location)
                url = rooturl._replace(path=str(Path(rooturl.path, path)))
                return url

        if self.conf.allow_direct_path_resolution:
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

    def collect_projects(self) -> Generator[ProjectMetadata, None, None]:
        """ Collect projects metadata from search paths
        """
        for url in self.conf.search_paths.values():
            try:
                handler = self.get_protocol_handler(url.scheme)
                yield from handler.projects(url)
            except Exception:
                logger.error(traceback.format_exc())

    def checkout(self, url: Url) -> Tuple[CatalogEntry, CheckoutStatus]:
        """ Checkout a project from a key
        """
        handler = self.get_protocol_handler(url.scheme)

        md = handler.project_metadata(url)
        e = self._catalog.get(md.uri)
        if e:
            if not e.project or md.last_modified > e.md.last_modified:
                entry = CatalogEntry(md, handler.project(md, self.conf))
                self._catalog[md.uri] = entry
                return (entry, CheckoutStatus.UPDATED)
            else:
                return (e, CheckoutStatus.UNCHANGED)
        else:
            # Insert new project
            entry = CatalogEntry(md, handler.project(md, self.conf))
            self._catalog[md.uri] = entry
            return (entry, CheckoutStatus.NEW)

    def peek(self, url: Url) -> Optional[CatalogEntry]:
        """ Peek an entry in the catalog
        """
        handler = self.get_protocol_handler(url.scheme)
        return self._catalog.get(handler.resolve_uri(url))

    def update(self, url: Url) -> Optional[CatalogEntry]:
        """ Update specific catalog entry

            Return the updated catalog entry or None
            if no entry has been updated
        """
        handler = self.get_protocol_handler(url.scheme)

        e = self._catalog[handler.resolve_uri(url)]
        md = handler.project_metadata(url)
        if md.modified_time > e.md.modified_time:
            if e.project:
                entry = CatalogEntry(md, handler.project(md, self.conf))
            else:
                entry = CatalogEntry(md, None)
            self._catalog[md.uri] = entry
            return entry
        else:
            return None

    def update_catalog(self) -> Generator[CatalogEntry, None, None]:
        """ Update the whole catalog

            Yield updated catalog entries
        """
        for e in self._catalog.values():
            handler = self.get_protocol_handler(e.md.scheme)
            md = handler.project_metadata(e.md)
            if md.modified_time > e.md.modified_time:
                if e.project:
                    entry = CatalogEntry(md, handler.project(md, self.conf))
                else:
                    entry = CatalogEntry(md, None)
                self._catalog[md.uri] = entry
                yield entry

    def refresh_catalog(self):
        """ Completely refresh the catalog

            Update all entries and reload outdated projects.
        """
        catalog = self._catalog
        self._catalog = {}
        for md in self.collect_projects():
            e = catalog.get(md.uri)
            if e:
                if md.modified_time > e.md.modified_time:
                    if e.project:
                        handler = self.get_protocol_handler(md.scheme)
                        entry = CatalogEntry(md, handler.project(md, self.conf))
                    else:
                        entry = CatalogEntry(md, None)
                else:
                    entry = e
            else:
                entry = CatalogEntry(md, None)

            self._catalog[md.uri] = entry
