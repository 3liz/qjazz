"""
Handle projects stored on S3 compatible object storage

Urls must be of the form s3://bucket/[prefix/]{path}

Limitations:

- With Gdal < 3.6 (Ubuntu 22.04), only one configuration is allowed
  since we cannot set a per prefix configuration.

- Per prefix configuration use the bucket/path as discriminating key, because of
  this is not possible to use the same bucket/path with two distinct
  configuration.

- Layers must be gdal /vsiXXX/ compatible - i.e, provider must be gdal or ogr
  Other layers must be downloaded locally.

- Projects must be created with the `force_readonly_layers` option.

- Not thread safe
"""

import os

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import (
    Iterator,
    Optional,
    cast,
)
from urllib.parse import urlsplit

from minio import Minio, S3Error
from osgeo.gdal import __version__ as __gdal_version__
from pydantic import DirectoryPath, FilePath, SecretStr

from qgis.core import Qgis, QgsPathResolver, QgsProject

from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import assert_precondition
from qjazz_contrib.core.config import ConfigSettings

from ..common import ProjectMetadata, ProtocolHandler, Url
from ..errors import InvalidCacheRootUrl
from ..storage import ProjectLoaderConfig, load_project_from_uri

if Qgis.QGIS_VERSION_INT < 33800:
    import warnings

    warnings.warn(f"S3 storage connector requires Qgis version > 3.38 (found {Qgis.version()})")

gdal_version_info = tuple(int(n) for n in __gdal_version__.split("."))

# Allowed files suffix for projects
PROJECT_SFX = ".qgz"


@contextmanager
def s3_storage_preprocessor(prefix: str):
    """Convert relative local path to
    vsis3 handler
    """

    def to_vsis3(path: str) -> str:
        if path.startswith("./"):
            logger.debug("[S3] converting --> %s", path)
            path = f"/vsis3/{prefix}/{path[2:]}"
        return path

    # XXX Calling setPathPreprocessor with QGIS 3.34
    # cause a segfault
    # cf https://github.com/qgis/QGIS/issues/58112
    ident = QgsPathResolver.setPathPreprocessor(to_vsis3)
    try:
        yield
    finally:
        QgsPathResolver.removePathPreprocessor(ident)


class S3HandlerConfig(ConfigSettings):
    endpoint: str
    access_key: str
    secret_key: SecretStr
    region: Optional[str] = None
    # SSL configuration
    cafile: Optional[FilePath] = None
    secure: bool = True
    check_cert: bool = True

    download_dir: Optional[DirectoryPath] = None


class S3ProtocolHandler(ProtocolHandler):
    """Protocol class for protocol handler"""

    Config = S3HandlerConfig

    def __init__(self, conf: S3HandlerConfig):
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

        self._download_dir = conf.download_dir
        self._tmpdirs: dict[str, TemporaryDirectory] = {}
        self._configured = False

    def validate_rooturl(self, rooturl: Url, config: ProjectLoaderConfig, is_dynamic: bool = False):
        """Validate the rooturl format"""
        if not config.force_readonly_layers:
            raise InvalidCacheRootUrl(
                "S3 handler does not support writable layers, use force_readonly_layers=True",
            )

        # Check that the bucket exists
        bucket = rooturl.hostname
        prefix = rooturl.path.strip("/")

        if not bucket:
            raise InvalidCacheRootUrl(
                ("Invalid S3 root url '{rooturl.geturl()}', expecting '{scheme}://{bucket}/[prefix/]'"),
            )
        if not self._client.bucket_exists(bucket):
            logger.warning(f"S3 Bucket '{bucket}' does not exists on target {self._conf.endpoint}")

        if gdal_version_info >= (3, 6):
            from osgeo.gdal import SetPathSpecificOption

            if prefix and is_dynamic:
                # Because gdal options are set at early stage prefix is no supported
                # in rooturl
                raise InvalidCacheRootUrl(
                    f"Dynamic s3 root url does not support prefix: {rooturl}"
                )

            key = f"/vsis3/{bucket}/{prefix}" if prefix else f"/vsis3/{bucket}"

            logger.debug("Adding S3 configuration for prefix %s", key)

            secret_key = self._conf.secret_key.get_secret_value()

            # XXX Require GDAL 3.6+
            # See https://gdal.org/en/latest/user/virtual_file_systems.html#vsis3-aws-s3-files
            # for options
            SetPathSpecificOption(key, "AWS_S3_ENDPOINT", self._conf.endpoint)
            SetPathSpecificOption(key, "AWS_ACCESS_KEY_ID", self._conf.access_key)
            SetPathSpecificOption(key, "AWS_SECRET_ACCESS_KEY", secret_key)
            SetPathSpecificOption(key, "AWS_REGION", self._conf.region)
            SetPathSpecificOption(key, "AWS_VIRTUAL_HOSTING", "FALSE")
            SetPathSpecificOption(key, "AWS_HTTPS", "YES" if self._conf.secure else "NO")
        elif not self._configured:
            from osgeo.gdal import SetConfigOption

            secret_key = self._conf.secret_key.get_secret_value()

            SetConfigOption("AWS_S3_ENDPOINT", self._conf.endpoint)
            SetConfigOption("AWS_ACCESS_KEY_ID", self._conf.access_key)
            SetConfigOption("AWS_SECRET_ACCESS_KEY", secret_key)
            SetConfigOption("AWS_REGION", self._conf.region)
            SetConfigOption("AWS_VIRTUAL_HOSTING", "FALSE")
            SetConfigOption("AWS_HTTPS", "YES" if self._conf.secure else "NO")

            self._configured = True
        else:
            logger.warning(
                f"Dropped S3  configuration for '{rooturl.geturl()}'\n"
                "GDAL version is < 3.6\n"
                "VSIS3 options connot be set on a per-prefix basis\n"
                "Only one s3 configuration is allowed"
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

    def project_metadata(self, url: Url | ProjectMetadata) -> ProjectMetadata:
        """Return project metadata"""
        if isinstance(url, ProjectMetadata):
            url = urlsplit(url.uri)

        bucket_name = url.hostname
        object_name = url.path

        assert_precondition(bucket_name is not None)
        bucket_name = cast(str, bucket_name)

        try:
            if not object_name.endswith(PROJECT_SFX):
                object_name = f"{object_name}{PROJECT_SFX}"
            stat = self._client.stat_object(bucket_name, object_name)
        except S3Error as err:
            match err.code:
                case "NoSuchBucket":
                    uri = url.geturl()
                    logger.error("S3 operation failed for '%s': %s", uri, err.message)
                    raise FileNotFoundError(uri) from None
                case "NoSuchKey":
                    raise FileNotFoundError(url.geturl()) from None
                case _:
                    raise

        assert_precondition(stat.last_modified is not None)
        last_modified = cast(datetime, stat.last_modified)

        return ProjectMetadata(
            uri=url._replace(path=object_name).geturl(),
            name=PurePosixPath(url.path).stem,
            scheme=url.scheme,
            storage="s3",
            last_modified=int(last_modified.timestamp()),
        )

    def project(self, md: ProjectMetadata, config: ProjectLoaderConfig) -> QgsProject:
        """Return project associated with metadata"""
        assert_precondition(Qgis.QGIS_VERSION_INT >= 33800, "Qgis 3.38+ required")
        assert_precondition(config.force_readonly_layers)

        uri = urlsplit(md.uri)
        bucket_name = uri.hostname
        object_name = uri.path

        assert_precondition(bucket_name is not None)
        bucket_name = cast(str, bucket_name)

        # Download project in tmpdir
        resp = self._client.get_object(bucket_name, object_name)
        match resp.status:
            case 404:
                raise FileNotFoundError(md.uri)
            case st if st > 200:
                logger.error(
                    "[S3] returned error %s: '%s'",
                    resp.status,
                    resp.read().decode(),
                )
                raise RuntimeError(f"S3 error {md.uri}: error {resp.status}: {resp.read().decode()}")
            case _:
                # Result ok
                pass

        object_path = PurePosixPath(bucket_name, object_name.strip("/"))

        tmpdir = TemporaryDirectory(
            prefix="s3_",
            dir=self._download_dir,
            ignore_cleanup_errors=True,
        )

        basename = object_path.name
        filename = Path(tmpdir.name).joinpath(basename)

        with filename.open("wb") as fp:
            for chunk in resp.stream():
                fp.write(chunk)

        resp.release_conn()

        # Store the download dir for later removal
        self._tmpdirs[md.uri] = tmpdir

        # Load the project
        logger.debug("[S3] Loading project from '%s'", filename)

        with s3_storage_preprocessor(f"{object_path.parent}"):
            return load_project_from_uri(f"{filename}", config)

    def projects(self, uri: Url) -> Iterator[ProjectMetadata]:
        """List all projects availables from the given uri"""
        bucket_name = uri.hostname
        prefix = uri.path.lstrip("/")

        assert_precondition(bucket_name is not None)
        bucket_name = cast(str, bucket_name)

        for obj in self._client.list_objects(bucket_name, prefix, recursive=True):
            path = PurePosixPath(obj.object_name)

            if path.suffix == ".qgz":
                assert_precondition(obj.last_modified is not None)
                last_modified = cast(datetime, obj.last_modified)

                yield ProjectMetadata(
                    uri=uri._replace(path=f"{path}").geturl(),
                    name=path.stem,
                    scheme=uri.scheme,
                    storage="s3",
                    last_modified=int(last_modified.timestamp()),
                )
