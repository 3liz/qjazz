""" Postgres storage handler
"""
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from pydantic import (
    Field,
    FilePath,
)
from typing_extensions import Dict, Optional

from qjazz_contrib.core import componentmanager
from qjazz_contrib.core.condition import assert_postcondition
from qjazz_contrib.core.config import ConfigSettings

from ..common import Url
from ..errors import InvalidCacheRootUrl
from .storage import ProjectLoaderConfig, QgisStorageProtocolHandler


def _parameters(url: Url) -> Dict[str, str]:
    return dict(parse_qsl(url.query))


class GeopackageHandlerConfig(ConfigSettings, env_prefix="conf_storage_geopackage_"):
    """ Geopackage handler settings
    """
    path: FilePath = Field(title="Path to geopackage")


@componentmanager.register_factory('@3liz.org/cache/protocol-handler;1?scheme=geopackage')
class GeoPackageHandler(QgisStorageProtocolHandler):

    Config = GeopackageHandlerConfig

    def __init__(self, conf: Optional[GeopackageHandlerConfig] = None):

        super().__init__('geopackage')

        self._path: Optional[FilePath] = None
        if conf:
            self._path = conf.path

    def validate_rooturl(self, rooturl: Url, config: ProjectLoaderConfig):

        if rooturl.path and self._path:
            raise InvalidCacheRootUrl(
                f"Path redefiniton in geopackage root url configuration: {rooturl.geturl()}",
            )

        if rooturl.path and not Path(rooturl.path).exists():
            raise InvalidCacheRootUrl(f"Geopackage {rooturl.path} does not exists")

        q = _parameters(rooturl)
        if "projectName" not in q:
            raise InvalidCacheRootUrl(
                "Missing 'projectName' parameter in geopackage root url {rooturl.geturl()}.\n"
                "If the project is from the input path then use 'projectName={path}' template"
                "as parameter.",
            )

    def resolve_uri(self, url: Url) -> str:
        #
        # Return the storage uri
        #
        q = _parameters(url)

        # Allow overriding config project Name
        project = q.get('projectName')
        path = Path(url.path) if url.path else self._path

        assert_postcondition(bool(path), "No geopackage path defined !")
        assert_postcondition(bool(project), "No project name defined !")

        return f"geopackage:{path}?projectName={project}"

    def public_path(self, url: str | Url, location: str, rooturl: Url) -> str:

        path = Path(location)

        if isinstance(url, str):
            url = urlsplit(url)

        if _parameters(rooturl).get('projectName') == '{path}':  # noqa RUF027
            project = _parameters(url)['projectName']
            path = path.joinpath(project)

        return f"{path}"
