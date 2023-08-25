#
# Copyright 2020 3liz
# Author David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

""" File protocol handler
"""
from typing import Generator
from itertools import chain
from pathlib import Path

from qgis.core import QgsProject
from py_qgis_contrib.core import logger, componentmanager

from ..config import ProjectsConfig
from ..storage import (
    ProjectMetadata,
    file_metadata,
    load_project_from_uri,
)
from ..common import (
    Url,
    IProtocolHandler,
)

# Allowed files suffix for projects
PROJECT_SFX = ('.qgs', '.qgz')

__all__ = []


@componentmanager.register_factory('@3liz.org/cache/protocol-handler;1?scheme=file')
class FileProtocolHandler(IProtocolHandler):
    """ Handle file protocol
    """

    def __init__(self):
        pass

    def _check_filepath(self, path: Path) -> Path:
        """ Validate Qgis project file path, add necis
        """
        if not path.is_absolute():
            raise ValueError(f"file path must be absolute not {path}")

        exists = False
        if path.suffix not in PROJECT_SFX:
            for sfx in PROJECT_SFX:
                path = path.with_suffix(sfx)
                exists = path.is_file()
                if exists:
                    break

        return path

    def resolve_uri(self, uri: Url) -> str:
        """ Override
        """
        return Path(uri.path)

    def project_metadata(self, url: Url | ProjectMetadata) -> ProjectMetadata:
        """ Override
        """
        if isinstance(url, ProjectMetadata):
            path = Path(url.uri)
        else:
            path = self._check_filepath(Path(url.path))
        if not path.exists():
            raise FileNotFoundError(str(path))
        return file_metadata(path)

    def project(self, md: ProjectMetadata, config: ProjectsConfig) -> QgsProject:
        """ Override
        """
        return load_project_from_uri(md.uri, config)

    def projects(self, url: Url) -> Generator[ProjectMetadata, None, None]:
        """ List all projects availables from the given uri
        """
        path = Path(url.path)
        if not path.exists():
            logger.warning(f"{path} does not exists")
            return

        if path.is_dir():
            globpattern = '**/*.%s'
            files = chain(*(path.glob(globpattern % sfx) for sfx in ('qgs', 'qgz')))
            for p in files:
                yield file_metadata(p)
        else:
            yield file_metadata(path)
