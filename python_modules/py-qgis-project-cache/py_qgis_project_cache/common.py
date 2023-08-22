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

from abc import ABC, abstractmethod
from datetime import datetime
from typing_extensions import (
    NewType,
    Union,
    Generator,
    Optional,
    NamedTuple,
    Dict
)

from qgis.core import QgsProject

from py_qgis_contrib.core import componentmanager

from .config import ProjectsConfig

Url = NewType('Url', urllib.parse.SplitResult)

CACHE_MANAGER_CONTRACTID = '@3liz.org/cache-manager;1'


class ProjectMetadata(NamedTuple):
    uri: str
    name: str
    scheme: str
    storage: Optional[str]
    last_modified: int

    def _to_json_serializable(self) -> Dict:
        d = self._asdict()
        d.update(
            last_modified=datetime.fromtimestamp(
                self.last_modified
            ).astimezone().isoformat()+'Z'
        )
        return d


def get_cacheservice():
    return componentmanager.get_service(CACHE_MANAGER_CONTRACTID)


class IProtocolHandler(ABC):
    """ Abstract class for protocol handler
    """

    @abstractmethod
    def resolve_uri(self, url: Url) -> str:
        """ Sanitize uri for using as catalog key entry

            The returned uri must ensure unicity of the
            resource location

            Must be idempotent
        """
        ...

    @abstractmethod
    def project_metadata(self, url: Union[Url | ProjectMetadata]) -> ProjectMetadata:
        """ Return project metadate
        """
        ...

    @abstractmethod
    def project(self, md: ProjectMetadata, config: ProjectsConfig) -> QgsProject:
        """ Return project associated with metadata
        """
        ...

    @abstractmethod
    def projects(self, uri) -> Generator[ProjectMetadata, None, None]:
        """ List all projects availables from the given uri
        """
        ...
