#
# Copyright 2023 3liz
# Author David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

""" Generic protocol handler for Qgis storage
"""

from datetime import datetime
from typing import Iterator
from urllib.parse import urlunsplit

from qgis.core import QgsApplication, QgsProject, QgsProjectStorage

from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import (
    assert_postcondition,
    assert_precondition,
)

from ..common import ProjectMetadata, ProtocolHandler, Url
from ..storage import ProjectLoaderConfig, load_project_from_uri

__all__ = []  # type: ignore


#
# Storage protocol handler implementation
#


class QgisStorageProtocolHandler(ProtocolHandler):
    """ Handle Qgis storage
    """
    def __init__(self, storage: str):
        """ Retrieve the QgsProjectStorage
        """
        sr = QgsApplication.projectStorageRegistry()
        self._storage: QgsProjectStorage = sr.projectStorageFromType(storage)
        assert_postcondition(self._storage is not None)

    def project_metadata(self, url: Url | ProjectMetadata) -> ProjectMetadata:
        """ Override
        """
        if isinstance(url, ProjectMetadata):
            uri = url.uri
        else:
            uri = self.resolve_uri(url)

        # Precondition
        # If there is problem here, then it comes from the
        # path resolver configuration
        assert_precondition(
            self._storage.isSupportedUri(uri),
            f"Invalide uri for storage '{self._storage.type()}': {uri}",
        )
        return self._project_storage_metadata(uri, url.scheme)

    def project(self, md: ProjectMetadata, config: ProjectLoaderConfig) -> QgsProject:
        """ Override
        """
        return load_project_from_uri(md.uri, config)

    def projects(self, url: Url) -> Iterator[ProjectMetadata]:
        """ Override
        """
        uri = urlunsplit(url)
        # Precondition
        # If there is problem here, then it comes from the
        # path resolver configuration
        assert_precondition(
            self._storage.isSupportedUri(uri),
            f"Unsupported {uri} for '{self._storage.type()}'",
        )

        for _uri in self._storage.listProjects(uri):
            yield self._project_storage_metadata(_uri, url.scheme)

    def _project_storage_metadata(self, uri: str, scheme: str) -> ProjectMetadata:
        """ Read metadata about project
        """
        res, md = self._storage.readProjectStorageMetadata(uri)
        if not res:
            logger.error("Failed to read storage metadata for %s", uri)
            raise FileNotFoundError(uri)
        # XXX
        last_modified = md.lastModified.toPyDateTime()
        return ProjectMetadata(
            uri=uri,
            name=md.name,
            scheme=scheme,
            storage=self._storage.type(),
            last_modified=int(datetime.timestamp(last_modified)),
        )
