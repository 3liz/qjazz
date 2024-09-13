

from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from typing_extensions import (
    Iterator,
    Union,
)

from qgis.core import QgsProject

from ..common import ProjectMetadata
from ..config import ProjectsConfig
from ..storage import UnreadableResource

Url = SplitResult


class DummyProtocolHandler:

    """ Protocol class for protocol handler
    """
    def resolve_uri(self, uri: Url) -> str:
        """ Override
        """
        return uri.geturl()

    def public_path(self, url: str | Url, location: str, rooturl: Url) -> str:
        """ Override
        """
        if isinstance(url, str):
            url = urlsplit(url)
        relpath = Path(url.path).relative_to(rooturl.path)
        return str(Path(location).joinpath(relpath))

    def project_metadata(self, url: Union[Url | ProjectMetadata]) -> ProjectMetadata:
        """ Return project metadata
        """
        uri = url.uri if isinstance(url, ProjectMetadata) else url.geturl()
        raise FileNotFoundError(uri)

    def project(self, md: ProjectMetadata, config: ProjectsConfig) -> QgsProject:
        """ Return project associated with metadata
        """
        raise UnreadableResource(md.uri)

    def projects(self, uri: Url) -> Iterator[ProjectMetadata]:
        """ List all projects availables from the given uri
        """
        return iter(())
