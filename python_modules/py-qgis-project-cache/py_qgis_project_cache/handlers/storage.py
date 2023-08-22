#
# Copyright 2023 3liz
# Author David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

""" Generic protocol handler for Qgis storage
"""
import traceback

from typing import Union, Generator, Optional, Callable, Dict
from urllib.parse import urlunsplit, parse_qs, urlencode
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsProject,
    QgsProjectStorage,
)

from py_qgis_contrib.core import logger, componentmanager

from ..config import ProjectsConfig
from ..storage import (
    ProjectMetadata,
    project_storage_metadata,
    list_storage_projects,
    load_project_from_uri,
)

from ..common import (
    Url,
    IProtocolHandler,
)

__all__ = []


RESOLVERS = {}


def resolver_for(name: str):
    """ Decorator for resolver
    """
    def wrapper(fn):
        RESOLVERS[name] = fn
        return fn
    return wrapper

#
# Default storage uri resolvers
#


@resolver_for('postgresql')
def postgresql_resolver(url: Url) -> str:
    qs = parse_qs(url.query)
    if 'project' not in qs:
        qs['project'] = [url.path]
        qs = urlencode(qs, doseq=True)
        url = url._replace(path="", query=qs)
    return urlunsplit(url)


@resolver_for('geopackage')
def geopackage_resolver(url: Url) -> str:
    qs = parse_qs(url.query)
    if 'projectName' not in qs:
        qs['projectName'] = [url.path]
        qs = urlencode(qs, doseq=True)
        url = url._replace(path="", query=qs)
    return urlunsplit(url)

#
# Handlers registration
#


def register_handlers(resolvers: Optional[Dict[str, Callable[[Url], str]]] = None):
    """ Register storage handlers as protocol handlers
    """
    resolvers = resolvers or RESOLVERS
    sr = QgsApplication.projectStorageRegistry()
    for ps in sr.projectStorages():
        storage = ps.type()
        logger.info("### Registering storage handler for %s", storage)
        componentmanager.gComponentManager.register_service(
            f'@3liz.org/cache/protocol-handler;1?scheme={storage}',
            QgisStorageProtocolHandler(ps, resolvers.get(storage)),
        )


def load_resolvers(confdir: Path):
    """ Load resolvers configuration
    """
    resolver_file = confdir.join('resolver.py')
    if resolver_file.exists():
        logger.info("Loading resolvers for qgis storage")
        with resolver_file.open() as source:
            try:
                exec(source.read(), {
                    'resolver_for': resolver_for,
                    'qgis_version': Qgis.QGIS_VERSION_INT,
                })
            except Exception:
                traceback.print_exc()
                raise RuntimeError(f"Failed to load resolver '{resolver_file}'") from None
    else:
        logger.info("No storage resolvers found")


def init_storage_handlers(confdir: Optional[Path]):
    """ Intialize storage handlers from resolver file
    """
    if confdir:
        load_resolvers(confdir)
    register_handlers()

#
# Storage protocol handler implementation
#


class QgisStorageProtocolHandler(IProtocolHandler):
    """ Handle postgres protocol
    """

    def __init__(
            self,
            storage: QgsProjectStorage,
            resolver: Optional[Callable[[Url], str]] = None,
    ):
        self._storage = storage
        self._resolver = resolver

    def resolve_uri(self, url: Url) -> str:
        """ Override
        """
        return self._resolver(url) if self._resolver else url

    def project_metadata(self, url: Union[Url | ProjectMetadata]) -> ProjectMetadata:
        """ Override
        """
        if isinstance(url, ProjectMetadata):
            uri = url.uri
        else:
            uri = self.resolve_uri(url)
        return project_storage_metadata(uri, self._storage)

    def project(self, md: ProjectMetadata, config: ProjectsConfig) -> QgsProject:
        """ Override
        """
        return load_project_from_uri(md.uri, config)

    def projects(self, url: Url) -> Generator[ProjectMetadata, None, None]:
        """ Override
        """
        return list_storage_projects(url, self._storage)
