""" Postgres storage handler
"""
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

from pydantic import (
    AnyUrl,
    Field,
    UrlConstraints,
)
from typing_extensions import Annotated, Dict, Optional

from qjazz_contrib.core import componentmanager
from qjazz_contrib.core.config import ConfigSettings

from ..common import Url
from ..errors import InvalidCacheRootUrl, ResourceNotAllowed
from .storage import ProjectLoaderConfig, QgisStorageProtocolHandler


def _parameters(url: Url | AnyUrl) -> Dict[str, str]:
    return dict(parse_qsl(url.query))


PostgresURL = Annotated[
    AnyUrl,
    UrlConstraints(
        allowed_schemes=["postgresql"],
        host_required=False,
    ),
]


class PostgresHandlerConfig(ConfigSettings, env_prefix="conf_storage_postgres_"):
    """ Postgres handler settings

        Qgis takes postgres project storage uri as
        postgresql://[user[:pass]@]host[:port]/?dbname=X&schema=Y&project=Z

        Enable database or/and project being specified from path
    """
    uri: PostgresURL = Field(
        title="Base postgresql uri",
        description="The base uri as QGIS postgres storage uri",
    )


@componentmanager.register_factory('@3liz.org/cache/protocol-handler;1?scheme=postgresql')
class PostgresHandler(QgisStorageProtocolHandler):

    Config = PostgresHandlerConfig

    def __init__(self, conf: Optional[PostgresHandlerConfig] = None):

        super().__init__('postgresql')

        conf = conf or PostgresHandlerConfig(uri="postgresql://")

        self._uri = urlsplit(str(conf.uri))
        self._query = _parameters(self._uri)

    def validate_rooturl(self, rooturl: Url, config: ProjectLoaderConfig):
        if rooturl.netloc and self._uri.netloc:
            raise InvalidCacheRootUrl(
                f"Netloc redefiniton in postgresql root url configuration: {rooturl.geturl()}",
            )

    def resolve_uri(self, url: Url) -> str:
        #
        # Return the storage uri
        # The target uri may define schema, dbname or project
        # and will override the configuration uri parameters.
        #
        q = self._query.copy()
        q.update(_parameters(url))

        project = q.get('project')
        parts = Path(url.path).parts
        match len(parts):
            case 1 if not project:
                q['project'] = parts[0]
            case 0 if project:
                pass
            case _:
                raise ResourceNotAllowed(url.path)

        netloc = self._uri.netloc or url.netloc

        uri = self._uri._replace(path="", netloc=netloc, query=urlencode(q))
        return uri.geturl()

    def public_path(self, url: str | Url, location: str, rooturl: Url) -> str:
        # Get configuration values
        q = self._query.copy()
        q.update(_parameters(rooturl))

        project = q.get('project')

        if isinstance(url, str):
            url = urlsplit(url)

        params = _parameters(url)

        path = Path(location)
        if not project:
            path = path.joinpath(params['project'])

        return f"{path}"
