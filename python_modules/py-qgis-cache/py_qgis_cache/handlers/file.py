#
# Copyright 2020 3liz
# Author David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

""" File protocol handler
"""
from itertools import chain
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit

from qgis.core import QgsProject

from py_qgis_contrib.core import componentmanager, logger

from ..common import IProtocolHandler, ProjectMetadata, Url
from ..config import ProjectsConfig
from ..storage import load_project_from_uri

# Allowed files suffix for projects
PROJECT_SFX = ('.qgs', '.qgz')

__all__ = []


def file_metadata(path: Path):
    st = path.stat()
    return ProjectMetadata(
        uri=str(path),
        name=path.stem,
        scheme='file',
        storage='file',
        last_modified=st.st_mtime
    )


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

    def public_path(self, url: str | Url, location: str, rooturl: Url) -> str:
        """ Override
        """
        if not isinstance(url, Url):
            url = urlsplit(url)
        relpath = Path(url.path).relative_to(rooturl.path)
        return str(Path(location).joinpath(relpath))

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

    def projects(self, url: Url) -> Iterator[ProjectMetadata]:
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
