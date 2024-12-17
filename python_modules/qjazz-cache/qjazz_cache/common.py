#
# Copyright 2020 3liz
# Author David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

""" Common definitions
"""
import urllib.parse

from abc import abstractmethod
from dataclasses import dataclass

from typing_extensions import (
    Iterator,
    Optional,
    Protocol,
    runtime_checkable,
)

from qgis.core import QgsProject

from .storage import ProjectLoaderConfig

Url = urllib.parse.SplitResult


@dataclass(frozen=True)
class ProjectMetadata:
    uri: str
    name: str
    scheme: str
    storage: Optional[str]
    last_modified: int


@runtime_checkable
class ProtocolHandler(Protocol):
    """ Protocol class for protocol handler
    """
    @abstractmethod
    def validate_rooturl(self, rooturl: Url, config: ProjectLoaderConfig):
        """ Validate the rooturl format
        """
        ...

    @abstractmethod
    def resolve_uri(self, url: Url) -> str:
        """ Sanitize uri for using as catalog key entry

            The returned uri must ensure unicity of the
            resource location

            Must be idempotent
        """

    @abstractmethod
    def public_path(self, uri: str | Url, location: str, rooturl: Url) -> str:
        """ Given a search path and an uri corressponding to
            a resolved_uri for this handler, it returns the uri
            usable relative to the search path.

            This is practically the reverse of a
            `CacheManager::resolve_path + resolve_url` calls

            Use it if you need to return a public path for callers
        """

    @abstractmethod
    def project_metadata(self, url: Url | ProjectMetadata) -> ProjectMetadata:
        """ Return project metadata
        """

    @abstractmethod
    def project(self, md: ProjectMetadata, config: ProjectLoaderConfig) -> QgsProject:
        """ Return project associated with metadata
        """

    @abstractmethod
    def projects(self, uri: Url) -> Iterator[ProjectMetadata]:
        """ List all projects availables from the given uri
        """
