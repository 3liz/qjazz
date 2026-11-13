"""
Handle resources stored on S3 compatible object storage

Urls must be of the form s3://bucket/[prefix/]{path}

Limitations:

- Per prefix configuration use the bucket/path as discriminating key, because of
  this is not possible to use the same bucket/path with two distinct
  configuration.

- Not thread safe
"""

import os
import urllib.parse

from pathlib import Path, PurePosixPath
from typing import (
    Iterator,
    Optional,
    cast,
)
from urllib.parse import urlsplit, urlunsplit

from minio import Minio
from pydantic import FilePath, SecretStr

from qjazz_core import logger
from qjazz_core.condition import assert_precondition
from qjazz_core.config import ConfigSettings

from ..resources import (
    ResourceObject,
    ResourceReader,
)

Url = urllib.parse.SplitResult


# Typing only import


class S3StorageConfig(ConfigSettings):
    endpoint: str
    access_key: str
    secret_key: SecretStr
    region: Optional[str] = None
    # SSL configuration
    cafile: Optional[FilePath] = None
    secure: bool = True
    check_cert: bool = True

    # Resource link expiration in seconds
    resource_url_expiration: int = 3600


class S3StorageHandler:
    """S3 storage handler"""

    Config = S3StorageConfig

    def __init__(self, conf: S3StorageConfig):
        if conf.cafile:
            os.environ["SSL_CERT_FILE"] = str(conf.cafile)

        self._conf = conf
        self._client = Minio(
            conf.endpoint,
            access_key=conf.access_key,
            secret_key=conf.secret_key.get_secret_value(),
            secure=conf.secure,
            cert_check=conf.check_cert,
            region=conf.region,
        )

    def resolve_uri(self, url: Url) -> str:
        """Sanitize uri for using as catalog key entry

        The returned uri must ensure unicity of the
        resource location

        Must be idempotent
        """
        return url.geturl()

    def public_path(self, uri: str | Url, location: str, rooturl: Url) -> str:
        """Given a search path and an uri corressponding to
        a resolved_uri for this handler, it returns the uri
        usable relative to the search path.

        This is practically the reverse of a
        `CacheManager::resolve_path + resolve_url` calls

        Use it if you need to return a public path for callers
        """
        if isinstance(uri, str):
            uri = urlsplit(uri)

        prefix = rooturl.path.strip("/")
        relpath = PurePosixPath(uri.path).relative_to(prefix or "/")
        return str(Path(location).joinpath(relpath))

    #
    # Implement the ResourceStore Protocol
    #

    def get_resource(self, uri: Url, name: Optional[str] = None) -> Optional[ResourceReader]:
        """Return a resource reader url for the given uri"""

        bucket_name = uri.hostname
        object_name = uri.path

        assert_precondition(bucket_name is not None)
        bucket_name = cast("str", bucket_name)

        if name:
            object_name = str(PurePosixPath(object_name).joinpath(name))

        resp = self._client.get_object(bucket_name, object_name)

        def _close():
            resp.close()
            resp.release_conn()

        match resp.status:
            case 404:
                _close()
                return None
            case st if st > 200:
                body = resp.read().decode()
                logger.error(
                    "[S3] returned error %s: '%s'",
                    resp.status,
                    body,
                )
                _close()
                raise RuntimeError(f"S3 error {urlunsplit(uri)}: error {resp.status}: {body}")
            case _:
                return ResourceReader(
                    read=resp.read,
                    close=_close,
                    size=int(resp.headers.get("content-length", "0")),
                    content_type=resp.headers.get("content-type"),
                    uri=urlunsplit(uri),
                )

    def list_resources(self, uri: Url, subpath: Optional[str] = None) -> Iterator[ResourceObject]:
        """Return a resource download url for the given uri"""

        bucket_name = uri.hostname
        root = PurePosixPath(uri.path)

        path = root.joinpath(subpath) if subpath else root

        prefix: str | None = str(path).removeprefix("/")
        prefix = f"{prefix}/" if prefix and not prefix.endswith("/") else None

        assert_precondition(bucket_name is not None)
        bucket_name = cast("str", bucket_name)

        for obj in self._client.list_objects(bucket_name, prefix=prefix):
            yield ResourceObject(
                name=str(PurePosixPath(obj.object_name).relative_to(root)),
                size=obj.size,
                content_type=obj.content_type,
                last_modified=obj.last_modified,
                is_dir=obj.is_dir,
            )

    #
    # Implement the RemoteResources protocol
    #

    def fget_resource(self, uri: Url, name: Optional[str], dest: Path):
        bucket_name = uri.hostname
        object_name = uri.path

        assert_precondition(bucket_name is not None)
        bucket_name = cast("str", bucket_name)

        if name:
            # Append name to path
            object_name = str(PurePosixPath(object_name, name))

        self._client.fget_object(bucket_name, object_name, str(dest))
