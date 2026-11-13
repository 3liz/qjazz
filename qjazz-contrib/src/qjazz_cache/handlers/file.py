"""File protocol handler"""

from itertools import chain
from pathlib import Path
from typing import Iterator, Optional

from qgis.core import QgsProject

from qjazz_core import componentmanager, logger

from ..common import ProjectLoader, ProjectMetadata, ProtocolHandler, Url
from ..errors import InvalidCacheRootUrl, ResourceNotAllowed
from ..loader import ProjectLoaderConfig
from ..resources import (
    ResourceObject,
    ResourceReader,
)
from ..storages.file import FileStorageHandler

# Allowed files suffix for projects
PROJECT_SFX = (".qgs", ".qgz")


def file_metadata(path: Path) -> ProjectMetadata:
    st = path.stat()
    return ProjectMetadata(
        uri=str(path),
        name=path.stem,
        scheme="file",
        storage="file",
        last_modified=st.st_mtime,
    )


@componentmanager.register_factory("@3liz.org/cache/protocol-handler;1?scheme=file")
class FileProtocolHandler(ProtocolHandler):
    """Handle file protocol"""

    def __init__(self):
        self._storage = FileStorageHandler()

    def _check_filepath(self, path: Path) -> Path:
        """Validate Qgis project file path, add ncis"""
        if not path.is_absolute():
            raise ResourceNotAllowed(f"file path must be absolute not {path}")

        exists = False
        if path.suffix not in PROJECT_SFX:
            for sfx in PROJECT_SFX:
                path = path.with_suffix(sfx)
                exists = path.is_file()
                if exists:
                    break

        return path

    def validate_rooturl(self, rooturl: Url, config: ProjectLoaderConfig, is_dynamic: bool = False):
        """Validate the rooturl format
        Note that dynamic path will no be validated
        """
        if not is_dynamic and not Path(rooturl.path).exists():
            raise InvalidCacheRootUrl(f"{rooturl.path} does not exists")

    def resolve_uri(self, uri: Url) -> str:
        """Override"""
        return self._storage.resolve_uri(uri)

    def public_path(self, url: str | Url, location: str, rooturl: Url) -> str:
        """Override"""
        return self._storage.public_path(url, location, rooturl)

    def project_metadata(self, url: Url | ProjectMetadata) -> ProjectMetadata:
        """Override"""
        path = Path(url.uri) if isinstance(url, ProjectMetadata) else self._check_filepath(Path(url.path))
        if not path.exists():
            raise FileNotFoundError(str(path))
        return file_metadata(path)

    def load_project(self, md: ProjectMetadata, load_project_from_uri: ProjectLoader) -> QgsProject:
        """Override"""
        return load_project_from_uri(md.uri)

    def projects(self, url: Url) -> Iterator[ProjectMetadata]:
        """List all projects availables from the given uri"""
        path = Path(url.path)
        if not path.exists():
            logger.warning(f"{path} does not exists")
            return

        if path.is_dir():
            globpattern = "**/*.%s"
            files = chain(*(path.glob(globpattern % sfx) for sfx in ("qgs", "qgz")))
            for p in files:
                yield file_metadata(p)
        else:
            yield file_metadata(path)

    #
    # Implement the ResourceStore Protocol
    #

    def get_resource(self, uri: Url, name: Optional[str] = None) -> Optional[ResourceReader]:
        return self._storage.get_resource(uri, name)

    def list_resources(self, uri: Url, subpath: Optional[str] = None) -> Iterator[ResourceObject]:
        return self._storage.list_resources(uri, subpath)
